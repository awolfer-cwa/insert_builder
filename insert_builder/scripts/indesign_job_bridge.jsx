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
        var runningName = file.name.replace(/\.job$/i, ".running");
        file.rename(runningName);

        var runningFile = new File(queue.fsName + "/" + runningName);
        var job = parseJob(runningFile);

        try {
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
            writeStatus(job.status, false, error);
            runningFile.rename(runningName.replace(/\.running$/i, ".failed"));
        }
    }

    function poll() {
        var jobs = queue.getFiles("*.job");
        for (var i = 0; i < jobs.length; i++) {
            processJob(jobs[i]);
        }
    }

    var existing = app.idleTasks.itemByName(bridgeName);
    if (existing.isValid) {
        existing.remove();
    }

    var task = app.idleTasks.add({ name: bridgeName, sleep: 1000 });
    task.addEventListener(IdleEvent.ON_IDLE, poll);
}());
