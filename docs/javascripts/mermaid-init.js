// Mermaid initialization for Material for MkDocs
// Uses polling to wait for Mermaid CDN to load, then renders diagrams.
// Handles dark/light mode toggling and Material's SPA navigation.

(function () {
  function getScheme() {
    // Material stores the scheme on <body> or the palette input
    var body = document.body;
    if (body && body.getAttribute('data-md-color-scheme') === 'slate') return 'slate';
    var palette = document.querySelector('[data-md-color-scheme="slate"]');
    return palette ? 'slate' : 'default';
  }

  function isDarkMode() { return getScheme() === 'slate'; }

  function themeVars(dark) {
    return dark ? {
      primaryColor:        '#7c4dff',
      primaryTextColor:    '#e0e0e0',
      primaryBorderColor:  '#b388ff',
      lineColor:           '#b388ff',
      secondaryColor:      '#37474f',
      tertiaryColor:       '#263238',
      background:          '#1a1a2e',
      mainBkg:             '#2d2d44',
      nodeBorder:          '#7c4dff',
      clusterBkg:          '#1e2732',
      titleColor:          '#e0e0e0',
      edgeLabelBackground: '#263238'
    } : {
      primaryColor:        '#7c4dff',
      primaryTextColor:    '#1a1a2e',
      primaryBorderColor:  '#5e35b1',
      lineColor:           '#5e35b1',
      secondaryColor:      '#ede7f6',
      tertiaryColor:       '#f3e5f5',
      mainBkg:             '#ede7f6'
    };
  }

  function render() {
    if (typeof mermaid === 'undefined') return false;

    var dark = isDarkMode();
    mermaid.initialize({
      startOnLoad: false,
      theme: dark ? 'dark' : 'default',
      securityLevel: 'loose',
      themeVariables: themeVars(dark)
    });

    // Material for MkDocs renders: <pre class="mermaid"><code>SOURCE</code></pre>
    // We convert each unprocessed one to <div class="mermaid">SOURCE</div>
    document.querySelectorAll('pre.mermaid').forEach(function (pre) {
      if (pre.getAttribute('data-done')) return;
      pre.setAttribute('data-done', '1');
      var code = pre.querySelector('code');
      var src  = (code ? code.textContent : pre.textContent).trim();
      var div  = document.createElement('div');
      div.className   = 'mermaid';
      div.textContent = src;
      pre.replaceWith(div);
    });

    mermaid.run({ querySelector: '.mermaid:not([data-processed])' });
    return true;
  }

  // Poll until Mermaid is available, then render
  function waitAndRender() {
    if (!render()) setTimeout(waitAndRender, 100);
  }

  // Run on initial page load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', waitAndRender);
  } else {
    waitAndRender();
  }

  // Re-render after Material SPA navigation (popstate / pushState)
  // Material dispatches a custom event or we can listen for location changes
  var lastUrl = location.href;
  new MutationObserver(function () {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      setTimeout(waitAndRender, 200); // brief delay for new content to mount
    }
  }).observe(document.body, { childList: true, subtree: true });

  // Re-render on color scheme toggle
  new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      if (m.attributeName === 'data-md-color-scheme') {
        // Reset processed flags so diagrams re-render with new theme
        document.querySelectorAll('.mermaid[data-processed]').forEach(function (el) {
          el.removeAttribute('data-processed');
        });
        waitAndRender();
      }
    });
  }).observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });

}());
