// Install this file once in InDesign's Startup Scripts folder, then restart InDesign.
// It polls C:\carma\indesign_bridge\queue for .job files written by Python.
//
// Vendored from carma_controller/carma_controller/assets/indesign_job_bridge.jsx —
// production-insertbuilder is a standalone project with its own venv, so it
// carries its own copy rather than depending on that repo. Must stay
// byte-for-byte identical to the carma_controller original: both
// insert_builder and template_builder/ad_filer queue jobs against the same
// C:\carma\indesign_bridge\queue, watched by whichever copy of this file is
// actually installed.
(function () {
    var bridgeName = "carma_indesign_job_bridge";
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

    var existing = app.idleTasks.itemByName(bridgeName);
    if (existing.isValid) {
        existing.remove();
    }

    var task = app.idleTasks.add({ name: bridgeName, sleep: 1000 });
    task.addEventListener(IdleEvent.ON_IDLE, poll);
}());
