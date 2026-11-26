// journal_layout.jsx
// Install in InDesign's Startup Scripts folder is NOT required — this one is
// triggered by name via carma_controller's indesign_job_bridge.jsx, which
// calls app.doScript(script, ScriptLanguage.JAVASCRIPT) with no parameters.
// Because no parameters are passed in, job/result paths below are fixed,
// matching what journal_builder.py writes to.
//
// NOT independently tested against a real InDesign install — this is a
// faithful translation of journal_builder.rb / journal_layout_task.rb's
// logic into ExtendScript, but the DOM method/property names (exportFile
// signature, xmlElements indexing, page.place argument shape) should be
// verified against a real InDesign scripting session before trusting this
// in production.

#include "json2.jsx"

var JOB_PATH = "C:/carma/storage/insert_builder/journal_job.json";
var RESULT_PATH = "C:/carma/storage/insert_builder/journal_result.json";

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
        // Matches the Ruby original — tag-setting failure doesn't abort the build.
        $.writeln("Failed to set tags on template: " + e.message);
    }
}

function LayoutState(doc, pageXSize, pageYSize) {
    this.doc = doc;
    this.totalPages = doc.pages.length;
    this.currentPage = null;
    this.currentPageIndex = 0;
    this.pageXSize = pageXSize;
    this.pageYSize = pageYSize;
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
    var requiredYSpace = orderYSpacing + order.height;
    this.pageYPosition += orderYSpacing;

    if (this.pageYPositionMin + requiredYSpace > this.pageYMax) {
        throw new NoSpaceOnPage("Insufficient minimum y space on page");
    }
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
    var placed = this.currentPage.place(new File(order.document_path), [this.pageXPosition, this.pageYPosition]);

    // Changed 2026-11-27, second pass: the first fix (>= instead of ===)
    // only advanced pageYPositionMin when ONE item reached the page's right
    // edge. That's true for Ruby's real ads (normally full page width, one
    // per row), but filler items are deliberately narrow — bin-packing tiles
    // several of them side by side in a row, and none of them individually
    // reaches the edge. Confirmed on production-bak via live progress
    // logging: pageYPositionMin stayed frozen and the loop cycled the same
    // row forever, still never terminating after the first fix. Correct fix
    // is to track the deepest point ANY item placed in the row reaches, not
    // just one that happens to hit the edge exactly — this is a strict
    // superset of the old behavior (a lone full-width item is still just the
    // max of one item) and also fixes the same latent understatement for
    // real multi-item rows that incrementYPosition's space check relied on.
    var newMax = this.pageXPosition + order.width;
    if (this.pageXPositionMax < newMax) {
        this.pageXPositionMax = newMax;
    }
    var rowBottom = this.pageYPosition + order.height;
    if (this.pageYPositionMin < rowBottom) {
        this.pageYPositionMin = rowBottom;
    }
    this.pageYPosition += order.height;
    this.adInFirstRow = false;
    this.adInFirstColumn = false;

    // placed[0] is the placed item's parent page item — used by
    // UpdatePageNumberTask in Ruby via Links lookup; here we just read the
    // page name directly off the page we placed onto, which is simpler and
    // doesn't depend on Links collection indexing at all.
    return this.currentPage.name;
};

// --- Filler support — new capability, no Ruby precedent. ---------------
// Unlike real orders (fixed size, exception-driven column/page retry),
// fillers are chosen live: try the largest catalog candidate that fits
// exactly where we currently are, place it, move on. wouldFitHere is a
// non-throwing dry run so multiple candidates can be tried cheaply without
// unwinding a try/catch per attempt.
LayoutState.prototype.wouldFitHere = function (candidate) {
    var xSpacing = (this.adInFirstRow && this.adInFirstColumn) ? candidate.starting_page_x_pos : candidate.insert_spacing_x;
    if (this.pageXPositionMax + xSpacing + candidate.width > this.pageXMax) {
        return false;
    }

    var ySpacing = this.adInFirstRow ? candidate.starting_page_y_pos : candidate.insert_spacing_y;
    if (this.pageYPositionMin + ySpacing + candidate.height > this.pageYMax) {
        return false;
    }
    if (this.pageYPosition + ySpacing + candidate.height > this.pageYMax) {
        return false;
    }
    return true;
};

// Mirrors what incrementXPosition/incrementYPosition do for a real order,
// but without throwing — wouldFitHere above already confirmed this fits.
LayoutState.prototype.commitPosition = function (candidate) {
    var xSpacing = (this.adInFirstRow && this.adInFirstColumn) ? candidate.starting_page_x_pos : candidate.insert_spacing_x;
    this.pageXPositionMax = this.pageXPositionMax + xSpacing;
    this.pageXPosition = this.pageXPositionMax;

    var ySpacing = this.adInFirstRow ? candidate.starting_page_y_pos : candidate.insert_spacing_y;
    this.pageYPosition += ySpacing;
};

LayoutState.prototype._firstFit = function (catalog) {
    for (var i = 0; i < catalog.length; i++) {
        if (this.wouldFitHere(catalog[i])) {
            return catalog[i];
        }
    }
    return null;
};

LayoutState.prototype.fillRemainingSpace = function (catalog) {
    var placements = [];
    if (catalog.length === 0) {
        return placements;
    }

    var loopCount = 0;
    while (true) {
        loopCount += 1;
        if (loopCount > 10000) {
            // Defense in depth, added 2026-11-27 after this loop hung
            // indefinitely on production-bak (runaway CPU, no termination)
            // due to a separate bug in insertOrder's row-full detection.
            // That bug is fixed, but incrementAdPosition already caps its
            // own retry loop at 20 iterations for the same reason — this
            // loop never had an equivalent cap.
            throw new Error("fillRemainingSpace loop exceeded 10000 iterations");
        }

        if (this.currentPage === null) {
            try {
                this.currentPage = this.incrementPage();
            } catch (e) {
                if (e.name === "NoPagesAvailable") { break; }
                throw e;
            }
        }

        var chosen = this._firstFit(catalog);

        if (chosen === null) {
            if (this.pageYPosition === 0 && this.pageXPositionMax === 0) {
                // Brand new page/row and even the smallest filler doesn't
                // fit — nothing more can be placed anywhere. Stop.
                break;
            }
            // Current column/row is exhausted for every catalog size —
            // move to a new row.
            this.pageYPosition = this.pageYPositionMin;
            if (this.pageYPosition === 0) { this.adInFirstRow = true; }
            this.pageXPositionMax = 0;
            this.pageXPosition = 0;
            this.adInFirstColumn = true;

            if (this._firstFit(catalog) === null) {
                // New row is no better — move to a new page entirely.
                this.currentPage = null;
            }
            continue;
        }

        this.commitPosition(chosen);
        var pageName = this.insertOrder(chosen);
        placements.push({ size_name: chosen.size_name, page_name: pageName });
    }

    return placements;
};

LayoutState.prototype.removeBlankPages = function () {
    var populatedPageCount = this.currentPageIndex;
    while (this.doc.pages.length > populatedPageCount) {
        this.doc.pages[this.doc.pages.length - 1].remove();
    }
};

LayoutState.prototype.checkPageCount = function (validPageCounts, fillerMasterName, leftMasterName, rightMasterName) {
    var count = this.doc.pages.length;
    var isValid = false;
    for (var i = 0; i < validPageCounts.length; i++) {
        if (validPageCounts[i] === count) { isValid = true; break; }
    }
    if (isValid) { return; }

    try {
        var fillerMaster = this.doc.masterSpreads.itemByName(fillerMasterName);
        var newPage = this.doc.pages.add(LocationOptions.AT_BEGINNING);
        newPage.appliedMaster = fillerMaster;
    } catch (e) {
        $.writeln("Failed to add cover page: " + e.message);
    }
    this.setMasterSpreads(leftMasterName, rightMasterName);
};

LayoutState.prototype.setMasterSpreads = function (leftMasterName, rightMasterName) {
    try {
        var masters = [this.doc.masterSpreads.itemByName(leftMasterName), this.doc.masterSpreads.itemByName(rightMasterName)];
        var pages = this.doc.pages;
        for (var i = 1; i < pages.length; i++) {
            pages[i].appliedMaster = masters[i % 2];
        }
    } catch (e) {
        $.writeln("Failed to set master spreads: " + e.message);
    }
};

function run() {
    var job;
    var doc;
    var result = { ok: false, error: null, placed_orders: [], unplaced_indexes: [] };

    // Defense in depth — indesign_job_bridge.jsx already sets this once at
    // InDesign startup, but this script does real document/export work that
    // could independently trigger InDesign's blocking "disable this event
    // handler?" dialog (see indesign_job_bridge.jsx for the full story), so
    // set it again here rather than assume it's still in effect.
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

    try {
        // readJob() used to be called before this try block. An uncaught
        // exception here (confirmed on production-bak, 2026-11-23: "JSON is
        // undefined" before the json2.jsx polyfill existed) escaped run()
        // entirely as a genuinely uncaught top-level script error crossing
        // app.doScript()'s boundary — not just an exception the bridge's own
        // try/catch sees downstream. That appears to be what silently
        // destabilizes InDesign's idle task afterward, even though the
        // bridge's own error handling looked correct. Nothing in run() may
        // ever throw outside this try again.
        job = readJob();

        // Diagnostic, 2026-11-24: app.open() failed with just the bare
        // message "open" on production-bak and the scratch directory was
        // already gone by the time we could inspect it (Python's own
        // cleanup runs the moment bridge.run_script() returns). Capture the
        // file's actual state up front so a repeat failure is debuggable
        // without racing that cleanup.
        var templateFile = new File(job.template_path);
        if (!templateFile.exists) {
            throw new Error("Template file does not exist: " + job.template_path);
        }
        if (templateFile.length === 0) {
            throw new Error("Template file is empty (0 bytes): " + job.template_path);
        }

        doc = app.open(templateFile);
        setTags(doc, job.tags);

        var state = new LayoutState(doc, job.page_x_size, job.page_y_size);
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

        // Fill whatever ad-sized gaps are left with Safety Insert fillers
        // before deciding what counts as a truly blank trailing page.
        result.filler_placements = state.fillRemainingSpace(job.filler_catalog || []);

        if (state.currentPageIndex < state.totalPages) {
            state.removeBlankPages();
        }
        state.checkPageCount(
            job.valid_page_counts,
            job.filler_master_spread_name,
            job.left_master_spread_name,
            job.right_master_spread_name
        );

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
