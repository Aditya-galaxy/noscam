// Runs first, before any of the page's own scripts. The demo pages carry their
// own copy of content.js for people without the extension; this attribute tells
// that copy the extension is here, so a page is never wired twice. It has to be
// on the DOM: the extension and the page each have their own `window`.
document.documentElement.setAttribute("data-noscam", "extension");
