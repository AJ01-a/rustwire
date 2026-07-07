/**
 * Theme bootstrap — runs synchronously in <head> (CSP forbids inline
 * scripts) so the saved theme applies before first paint, no flash.
 * Light is the default; "?theme=dark|light" previews without persisting.
 */
(function () {
  var theme = null;
  try {
    theme = new URLSearchParams(location.search).get("theme") ||
            localStorage.getItem("techpulse:theme");
  } catch (e) { /* storage disabled */ }
  if (theme !== "dark" && theme !== "light") theme = "light";
  document.documentElement.dataset.theme = theme;
})();
