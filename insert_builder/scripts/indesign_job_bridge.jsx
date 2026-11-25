// Install this file once in InDesign's Startup Scripts folder, then restart InDesign.
// It runs once at launch, processing whatever's already sitting in
// C:\carma\indesign_bridge\queue — no persistent idle task involved.
//
// FINAL DESIGN, 2026-11-26: app.idleTasks + ON_IDLE never fires in the
// default engine, and even #targetengine (a separate named engine) fired
// reliably for 12+ minutes on one test then zero times on an identical
// fresh restart — genuinely flaky, not fixable with more script changes.
// The one thing proven 100% reliable all day, every single time, is that
// this Startup Script itself runs fully on every InDesign launch. So Python
// (insert_builder/indesign/bridge.py's _restart_indesign()) now restarts
// InDesign before every single script trigger, and this just does one
// bounded poll() pass at launch instead of registering any kind of
// persistent listener.
(function () {
    // Confirmed on production-bak, 2026-11-24: InDesign shows a blocking,
    // modal, native dialog ("An attached script generated the following
    // error... Do you want to disable this event handler?") whenever an
    // idle task's callback hits certain errors — entirely separate from any
    // JS try/catch in our own code. While that dialog sits on screen
    // (possibly behind other windows, invisible to an unattended run),
    // InDesign's whole event loop is frozen: no further idle ticks, no
    // further doScript() calls, nothing — which is what silently killed
    // every previous attempt to get this bridge working unattended. This is
    // the documented way to suppress that class of dialog during scripted
    // execution.
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

    var root = new Folder("C:/carma/indesign_bridge");
    var queue = new Folder(root.fsName + "/queue");
    var results = new Folder(root.fsName + "/results");

    if (!root.exists) {
        root.create();
    }
    if (!queue.exists) {
        queue.create();
    }
    if (!results.exists) {
        results.create();
    }

    function parseJob(file) {
        var job = {};
        file.encoding = "UTF-8";
        if (!file.open("r")) {
            throw new Error("Unable to open job file: " + file.fsName);
        }

        while (!file.eof) {
            var line = file.readln();
            var index = line.indexOf("=");
            if (index > 0) {
                job[line.substring(0, index)] = line.substring(index + 1);
            }
        }
        file.close();
        return job;
    }

    function writeStatus(path, ok, message) {
        if (!path) {
            return;
        }

        var file = new File(path);
        file.encoding = "UTF-8";
        file.open("w");
        file.writeln("ok=" + (ok ? "1" : "0"));
        if (message) {
            file.writeln("error=" + String(message).replace(/[\r\n]+/g, " "));
        }
        file.close();
    }

    function processJob(file) {
        // Reproduced on production-bak, 2026-11-23, 100% repeatable: the
        // previous version renamed file -> .running, then built a BRAND NEW
        // File object from a hand-concatenated path (queue.fsName + "/" +
        // name) to reopen it — that reopen failed every single time, for
        // every job, regardless of InDesign focus/idle state. queue.fsName
        // is a backslash-style native Windows path; appending "/" onto it
        // mixes separator styles in one string, which this ExtendScript
        // engine's File constructor does not resolve back to the real file.
        //
        // Fix: never reconstruct a File object for a file we already hold a
        // reference to. Parse the job while `file` still has its original
        // name (no rename involved yet), then reuse the same `file` object
        // for every later operation — rename/remove on an existing object is
        // safe; rebuilding its path from a string is what was broken.
        var originalName = file.name;
        var job = null;

        try {
            job = parseJob(file);

            if (!job.script) {
                throw new Error("Job is missing script path");
            }

            var script = new File(job.script);
            if (!script.exists) {
                throw new Error("Script does not exist: " + job.script);
            }

            // Claim the job so a second poll tick can't double-process it
            // while doScript() is running. If the rename itself fails, we
            // still attempt the run rather than losing the job entirely —
            // Python only ever queues one job per distribution at a time, so
            // double-processing isn't a realistic risk in practice.
            file.rename(originalName.replace(/\.job$/i, ".running"));

            app.doScript(script, ScriptLanguage.JAVASCRIPT);
            writeStatus(job.status, true, "");
            file.remove();
        } catch (error) {
            if (job && job.status) {
                writeStatus(job.status, false, error);
            } else {
                // job.status isn't known because parseJob() itself failed —
                // fall back to a file next to the job so the failure is
                // still discoverable instead of silently vanishing.
                writeStatus(queue + "/" + originalName + ".error", false, error);
            }

            try {
                if (file.exists) {
                    file.rename(originalName.replace(/\.(job|running)$/i, ".failed"));
                }
            } catch (renameError) {
                // Nothing more we can do here — already logged via writeStatus above.
            }
        }
    }

    function poll() {
        var jobs = queue.getFiles("*.job");
        for (var i = 0; i < jobs.length; i++) {
            try {
                processJob(jobs[i]);
            } catch (error) {
                // Last-resort guard — processJob() already handles its own
                // errors, but nothing here may ever throw uncaught, since an
                // uncaught exception in an idle-task callback is exactly
                // what silently killed this task before.
            }
        }
    }

    poll();
}());
