// handbook_layout.jsx — see journal_layout.jsx for the shared caveats:
// triggered via carma_controller's generic bridge with no parameters passed
// in, so job/result paths are fixed; not independently tested against a
// real InDesign install.

#include "json2.jsx"

var JOB_PATH = "C:/carma/storage/insert_builder/handbook_job.json";
var RESULT_PATH = "C:/carma/storage/insert_builder/handbook_result.json";

function NoSpaceInColumn(message) { this.name = "NoSpaceInColumn"; this.message = message; }
function NoSpaceOnPage(message) { this.name = "NoSpaceOnPage"; this.message = message; }
function NoPagesAvailable(message) { this.name = "NoPagesAvailable"; this.message = message; }

function readJob() {
    var file = new File(JOB_PATH);
    file.encoding = "UTF-8";
    file.open("r");
    var text = file.read();
    file.close();
    return JSON.parse(text);
}

function writeResult(result) {
    var file = new File(RESULT_PATH);
    file.encoding = "UTF-8";
    file.open("w");
    file.write(JSON.stringify(result));
    file.close();
}

function setTags(doc, tags) {
    try {
        var root = doc.xmlElements[0];
        for (var i = 0; i < root.xmlElements.length; i++) {
            var element = root.xmlElements[i];
            var tagName = element.markupTag.name;
            if (tags.hasOwnProperty(tagName)) {
                element.contents = tags[tagName];
            }
        }
    } catch (e) {
        $.writeln("Failed to set tags on template: " + e.message);
    }
}

function LayoutState(doc, pageXSize, pageYSize, adInsertMasterName) {
    this.doc = doc;
    this.totalPages = doc.pages.length;
    this.currentPage = null;
    this.currentPageIndex = 0;
    this.pageXSize = pageXSize;
    this.pageYSize = pageYSize;
    this.adInsertMasterName = adInsertMasterName;
}

LayoutState.prototype.resetPage = function () {
    this.pageXPosition = 0;
    this.pageYPosition = 0;
    this.pageYPositionMin = 0;
    this.pageXPositionMax = 0;
    this.adInFirstRow = true;
    this.adInFirstColumn = true;
};

LayoutState.prototype.incrementPage = function () {
    var pageIndex = this.currentPageIndex + 1;
    if (pageIndex > this.totalPages) {
        throw new NoPagesAvailable("No more pages available");
    }
    var page = this.doc.pages[pageIndex - 1];
    this.currentPageIndex = pageIndex;

    // Handbook-specific: skip any page that isn't an ad-insert page (the
    // template may contain fixed cover/section pages interleaved).
    if (!page.appliedMaster || page.appliedMaster.name !== this.adInsertMasterName) {
        return this.incrementPage();
    }
    this.resetPage();
    return page;
};

LayoutState.prototype.incrementXPosition = function (order) {
    var orderXSpacing;
    if (this.adInFirstRow && this.adInFirstColumn) {
        orderXSpacing = order.starting_page_x_pos;
    } else {
        orderXSpacing = order.insert_spacing_x;
    }
    this.pageXPositionMax = this.pageXPositionMax + orderXSpacing;
    this.pageXPosition = this.pageXPositionMax;

    if (this.pageXPosition + order.width > this.pageXMax) {
        throw new NoSpaceOnPage("No horizontal space on page");
    }
};

LayoutState.prototype.incrementYPosition = function (order) {
    var orderYSpacing = this.adInFirstRow ? order.starting_page_y_pos : order.insert_spacing_y;
    this.pageYPosition += orderYSpacing;

    if (this.pageYPosition + order.height > this.pageYMax) {
        if (this.adInFirstRow) {
            throw new NoSpaceOnPage("No space at all on page");
        } else {
            throw new NoSpaceInColumn("No vertical space on page");
        }
    }
};

LayoutState.prototype.incrementAdPosition = function (order) {
    var incrementError = null;
    var loopCount = 0;
    while (true) {
        loopCount += 1;
        if (loopCount > 20) {
            throw new Error("Something went wrong — layout loop exceeded 20 iterations");
        }

        try {
            if (this.currentPage === null) {
                var page = this.incrementPage();
                this.incrementXPosition(order);
                this.currentPage = page;
            }

            if (incrementError === null) {
                this.incrementYPosition(order);
                return;
            } else if (incrementError.name === "NoSpaceInColumn") {
                this.pageYPosition = this.pageYPositionMin;
                // Ruby: `@ad_in_first_row = true unless @page_y_position != 0`
                // i.e. true only when pageYPosition is back to 0 — NOT the
                // inverse, which an earlier pass here had backwards.
                if (this.pageYPosition === 0) {
                    this.adInFirstRow = true;
                }
                this.incrementXPosition(order);
            } else if (incrementError.name === "NoSpaceOnPage") {
                this.currentPage = null;
            }
            incrementError = null;
        } catch (e) {
            if (e.name === "NoSpaceInColumn" || e.name === "NoSpaceOnPage") {
                incrementError = e;
            } else {
                throw e;
            }
        }
    }
};

LayoutState.prototype.insertOrder = function (order) {
    this.currentPage.place(new File(order.document_path), [this.pageXPosition, this.pageYPosition]);

    if (this.pageXPosition + order.width >= this.pageXMax) {
        // Changed 2026-11-27, mirroring the same fix in journal_layout.jsx:
        // exact equality almost never holds for real ad sizes, so this never
        // reliably detected a full row. Harmless for handbook today (no
        // unbounded loop depends on it), but it's the same latent row-full
        // detection bug ported from journal_layout_task.rb's Ruby original —
        // fixed here too before handbook's first live test.
        this.pageYPositionMin = this.pageYPosition + order.height;
    } else {
        var newMax = this.pageXPosition + order.width;
        if (this.pageXPositionMax < newMax) {
            this.pageXPositionMax = newMax;
        }
    }
    this.pageYPosition += order.height;
    this.adInFirstRow = false;
    this.adInFirstColumn = false;

    return this.currentPage.name;
};

function run() {
    var job;
    var doc;
    var result = { ok: false, error: null, placed_orders: [], unplaced_indexes: [] };

    // Defense in depth — see journal_layout.jsx / indesign_job_bridge.jsx
    // for why.
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

    try {
        // See journal_layout.jsx for why readJob() must be inside this try —
        // an exception escaping run() entirely (not just caught by the
        // bridge downstream) appears to destabilize InDesign's idle task.
        job = readJob();
        doc = app.open(new File(job.template_path));
        setTags(doc, job.tags);

        var state = new LayoutState(doc, job.page_x_size, job.page_y_size, job.ad_insert_master_spread_name);
        state.resetPage();

        if (job.orders.length > 0) {
            var first = job.orders[0];
            state.pageYMin = first.starting_page_y_pos;
            state.pageXMin = first.starting_page_x_pos;
            state.pageYMax = state.pageYMin + state.pageYSize;
            state.pageXMax = state.pageXMin + state.pageXSize;
        }

        for (var i = 0; i < job.orders.length; i++) {
            var order = job.orders[i];
            try {
                state.incrementAdPosition(order);
                var pageName = state.insertOrder(order);
                result.placed_orders.push({ index: order.index, page_name: pageName });
            } catch (e) {
                if (e.name === "NoPagesAvailable") {
                    result.unplaced_indexes.push(order.index);
                    break;
                }
                throw e;
            }
        }

        doc.save(new File(job.output_path));

        var pdfFormat = ExportFormat.PDF_TYPE;
        doc.exportFile(pdfFormat, new File(job.hi_res_pdf_path), false, app.pdfExportPresets.itemByName("[High Quality Print]"));
        doc.exportFile(pdfFormat, new File(job.lo_res_pdf_path), false, app.pdfExportPresets.itemByName("[Smallest File Size]"));

        doc.close(SaveOptions.NO);
        result.ok = true;
        result.final_page_count = state.doc.pages.length;
    } catch (e) {
        result.ok = false;
        result.error = e.message || String(e);
        try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
    }

    writeResult(result);
}

run();
