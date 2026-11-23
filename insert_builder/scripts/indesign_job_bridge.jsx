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
        // parseJob() and the rename() result used to be outside this try
        // block. On production-bak, one job file failed to open right after
        // rename (cause unconfirmed — possibly a transient lock), threw
        // uncaught, and silently disabled this entire idle task for the
        // rest of the InDesign session: it stayed registered
        // (idleTasks.itemByName(...).isValid kept reporting true) but never
        // fired again. Confirmed via manual reproduction, 2026-11-23.
        // Everything that can throw must now be inside this try, so a single
        // bad job can never take down the whole bridge.
        var runningName = file.name.replace(/\.job$/i, ".running");
        var failedName = runningName.replace(/\.running$/i, ".failed");
        var job = null;

        try {
            if (!file.rename(runningName)) {
                throw new Error("Unable to rename job file to " + runningName);
            }

            var runningFile = new File(queue.fsName + "/" + runningName);
            job = parseJob(runningFile);

            if (!job.script) {
                throw new Error("Job is missing script path");
            }

            var script = new File(job.script);
            if (!script.exists) {
                throw new Error("Script does not exist: " + job.script);
            }

            app.doScript(script, ScriptLanguage.JAVASCRIPT);
            writeStatus(job.status, true, "");
            runningFile.remove();
        } catch (error) {
            if (job && job.status) {
                writeStatus(job.status, false, error);
            } else {
                // job.status isn't known because parseJob() itself failed —
                // fall back to a file next to the job so the failure is
                // still discoverable instead of silently vanishing.
                writeStatus(queue.fsName + "/" + failedName + ".error", false, error);
            }

            var stuckFile = new File(queue.fsName + "/" + runningName);
            if (stuckFile.exists) {
                stuckFile.rename(failedName);
            } else {
                file.rename(failedName);
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
