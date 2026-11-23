// Minimal JSON polyfill for ExtendScript, which has no native JSON global
// (confirmed on production-bak, 2026-11-23: "ReferenceError: JSON is
// undefined" when journal_layout.jsx/handbook_layout.jsx called
// JSON.parse/JSON.stringify directly). Only needs to round-trip what
// Python's json.dumps() produces for our own job files (nested dicts/lists
// of strings, numbers, booleans, null) and what this script itself produces
// for the result file — not a general-purpose, spec-complete JSON library.
if (typeof JSON === "undefined") {
    var JSON = {};
}

if (!JSON.parse) {
    JSON.parse = function (text) {
        // Job files are written by our own trusted Python process, never by
        // untrusted input, so eval() is the standard ExtendScript-era
        // approach for this rather than hand-rolling a parser.
        return eval("(" + text + ")");
    };
}

if (!JSON.stringify) {
    JSON.stringify = (function () {
        function quoteString(s) {
            return '"' + String(s)
                .replace(/\\/g, "\\\\")
                .replace(/"/g, '\\"')
                .replace(/\n/g, "\\n")
                .replace(/\r/g, "\\r")
                .replace(/\t/g, "\\t") + '"';
        }

        return function stringify(value) {
            if (value === null || value === undefined) {
                return "null";
            }
            var type = typeof value;
            if (type === "number" || type === "boolean") {
                return String(value);
            }
            if (type === "string") {
                return quoteString(value);
            }
            if (value instanceof Array) {
                var items = [];
                for (var i = 0; i < value.length; i++) {
                    items.push(stringify(value[i]));
                }
                return "[" + items.join(",") + "]";
            }
            if (type === "object") {
                var pairs = [];
                for (var key in value) {
                    if (value.hasOwnProperty(key)) {
                        pairs.push(quoteString(key) + ":" + stringify(value[key]));
                    }
                }
                return "{" + pairs.join(",") + "}";
            }
            return "null";
        };
    }());
}
