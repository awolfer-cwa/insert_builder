// cleanup.jsx — feature #3. Closes any document InDesign still has open from
// a previous failed build, without saving, before the next run starts.
// Triggered via carma_controller's generic bridge (no parameters passed in),
// writes nothing of its own — the bridge's own status file is enough since
// this either succeeds or the bridge reports the thrown error.

for (var i = app.documents.length - 1; i >= 0; i--) {
    try {
        app.documents[i].close(SaveOptions.NO);
    } catch (e) {
        $.writeln("Failed to close document: " + e.message);
    }
}
