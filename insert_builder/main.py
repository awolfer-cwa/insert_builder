import argparse
import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from insert_builder.config.settings import settings
from insert_builder.database.provision import get_engine, get_active_tenants, get_single_tenant
from insert_builder.database.tenant import (
    get_tenant_engine,
    get_outstanding_distributions,
    get_outstanding_subdistributions,
    get_system_flag,
)
from insert_builder.filesystem.local import LocalFileHandler
from insert_builder.builder.journal_builder import build_journal
from insert_builder.builder.handbook_builder import build_handbook
from insert_builder.email.report import safe_send_email

PID_FILE = Path(r"C:\carma\run\insert_builder.pid")
STATUS_FILE = Path(r"C:\carma\run\insert_builder_status.json")
LOG_PATH = Path(r"C:\carma\log\insert_builder_python.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    handlers=[
        logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=100_000_000, backupCount=7),
        logging.StreamHandler(),
    ],
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Carma Insert Builder")
    parser.add_argument("--tenant", type=str, default=None, help="Single tenant database to process")
    parser.add_argument("--distribution", type=int, default=None, help="Single distribution to process")
    parser.add_argument("--subdistribution", type=int, default=None, help="Single subdistribution to process")
    args = parser.parse_args()

    # Preserved from insert_builder.rb's own validation — prevents a numeric
    # ID being applied against the wrong tenant, or two mutually exclusive
    # single-target runs being requested at once.
    if args.distribution is not None and args.subdistribution is not None:
        sys.exit("You may not specify both a distribution and subdistribution to run")
    if args.distribution is not None and args.tenant is None:
        sys.exit("A specific distribution can only be run if a tenant is specified as well")
    if args.subdistribution is not None and args.tenant is None:
        sys.exit("A specific subdistribution can only be run if a tenant is specified as well")
    return args


def _write_status(message: str) -> None:
    """Feature #4 hook point — writes current progress to a status file.
    Surfacing this through carma_controller's own /api/status endpoint needs
    a corresponding change there to read this file; that side isn't included
    here since it's a separate repo."""
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps({"message": message, "updated_at": datetime.now().isoformat()}))
    except Exception:
        logger.debug("Failed to write status file", exc_info=True)


def run() -> None:
    if PID_FILE.exists():
        logger.fatal("There already appears to be an instance of insert_builder running. Exiting.")
        return
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    try:
        args = parse_args()
        logger.info("-" * 50)
        logger.info("Insert Builder started")

        # No separate orphaned-document cleanup needed — every
        # bridge.run_script() call now restarts InDesign from scratch
        # (_restart_indesign(), added 2026-11-26), which already discards
        # any leftover document state from a previous failed run.

        provision_engine = get_engine(settings)
        with Session(provision_engine) as provision_session:
            tenants = (
                [get_single_tenant(provision_session, args.tenant)]
                if args.tenant
                else get_active_tenants(provision_session)
            )

            for tenant in tenants:
                if tenant is None:
                    continue
                logger.info("Connecting to tenant db at %s", tenant.name)
                tenant_engine = get_tenant_engine(tenant)
                with Session(tenant_engine) as session:
                    local_fs = LocalFileHandler(settings)
                    local_fs.ensure_storage_root()
                    file_ads_by_region = get_system_flag(session, "FileAdsByRegion")
                    file_ads_by_format = get_system_flag(session, "FileAdsByFormat")

                    if args.subdistribution is None:
                        _process_distributions(
                            session, settings, local_fs, tenant, args.distribution,
                            file_ads_by_region, file_ads_by_format,
                        )
                    if args.distribution is None:
                        _process_subdistributions(session, settings, local_fs, tenant, args.subdistribution)
    except Exception as e:
        logger.error("Insert Builder failed: %s", e, exc_info=True)
    finally:
        logger.info("Done!")
        if PID_FILE.exists():
            PID_FILE.unlink()


def _process_distributions(session, settings, local_fs, tenant, manual_distribution, file_ads_by_region, file_ads_by_format):
    distributions = get_outstanding_distributions(session, manual_distribution)
    if not distributions:
        logger.info("There are no outstanding distributions for %s", tenant.name)
        return

    logger.info("There are %d outstanding distributions for %s", len(distributions), tenant.name)
    for distribution in distributions:
        _write_status(f"Insert Builder: distribution {distribution.DistributionID}")
        try:
            success, error = build_journal(
                session, settings, local_fs, distribution, file_ads_by_region, file_ads_by_format
            )
        except Exception as e:
            success, error = False, str(e)
            logger.error("Distribution %s failed: %s", distribution.DistributionID, e, exc_info=True)

        if success:
            distribution.ReadyToRun = False
            safe_send_email("success", tenant, distribution)
        else:
            # Feature #2 — deliberately left ReadyToRun = True so this is
            # retried next cycle, instead of the Ruby original's blanket
            # `ensure` clause marking a half-finished build as done.
            logger.error("Distribution %s did not complete: %s", distribution.DistributionID, error)
            safe_send_email("failure", tenant, distribution, error)
        session.commit()


def _process_subdistributions(session, settings, local_fs, tenant, manual_subdistribution):
    subdistributions = get_outstanding_subdistributions(session, manual_subdistribution)
    if not subdistributions:
        logger.info("There are no outstanding subdistributions for %s", tenant.name)
        return

    logger.info("There are %d outstanding subdistributions for %s", len(subdistributions), tenant.name)
    for subdistribution in subdistributions:
        _write_status(f"Insert Builder: subdistribution {subdistribution.iSubDistributionID}")
        try:
            success, error = build_handbook(session, settings, local_fs, subdistribution)
        except Exception as e:
            success, error = False, str(e)
            logger.error("Subdistribution %s failed: %s", subdistribution.iSubDistributionID, e, exc_info=True)

        if success:
            subdistribution.ReadyToRun = False
            safe_send_email("success", tenant, subdistribution)
        else:
            logger.error("Subdistribution %s did not complete: %s", subdistribution.iSubDistributionID, error)
            safe_send_email("failure", tenant, subdistribution, error)
        session.commit()


if __name__ == "__main__":
    run()
