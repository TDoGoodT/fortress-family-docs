// Mermaid initialization for Material for MkDocs
// Handles dark/light mode and SPA navigation

function getMermaidTheme() {
  var el = document.querySelector('[data-md-color-scheme]');
  var scheme = el ? el.getAttribute('data-md-color-scheme') : 'default';
  return scheme === 'slate' ? 'dark' : 'default';
}

function getMermaidThemeVars(isDark) {
  return isDark ? {
    primaryColor: '#7c4dff',
    primaryTextColor: '#e0e0e0',
    primaryBorderColor: '#b388ff',
    lineColor: '#b388ff',
    secondaryColor: '#37474f',
    tertiaryColor: '#263238',
    background: '#1e1e2e',
    mainBkg: '#2d2d44',
    nodeBorder: '#7c4dff',
    clusterBkg: '#1e2732',
    titleColor: '#e0e0e0',
    edgeLabelBackground: '#263238'
  } : {
    primaryColor: '#7c4dff',
    primaryTextColor: '#1a1a2e',
    primaryBorderColor: '#5e35b1',
    lineColor: '#5e35b1',
    secondaryColor: '#ede7f6',
    tertiaryColor: '#f3e5f5',
    background: '#ffffff',
    mainBkg: '#ede7f6'
  };
}

function renderMermaid() {
  if (typeof mermaid === 'undefined') return;

  var isDark = getMermaidTheme() === 'dark';

  mermaid.initialize({
    startOnLoad: false,
    theme: isDark ? 'dark' : 'default',
    securityLevel: 'loose',
    themeVariables: getMermaidThemeVars(isDark)
  });

  // Material outputs: <pre class="mermaid"><code>...</code></pre>
  // Convert each unseen one to <div class="mermaid"> so Mermaid can process it
  document.querySelectorAll('pre.mermaid').forEach(function(pre) {
    if (pre.getAttribute('data-mermaid-done')) return;
    pre.setAttribute('data-mermaid-done', '1');
    var code = pre.querySelector('code');
    var src = code ? code.innerText : pre.innerText;
    var div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = src;
    pre.parentNode.replaceChild(div, pre);
  });

  mermaid.run({ querySelector: '.mermaid:not([data-processed])' });
}

// Wait until mermaid global is available (it loads async from CDN)
function waitForMermaid(callback, attempts) {
  attempts = attempts || 0;
  if (typeof mermaid !== 'undefined') {
    callback();
  } else if (attempts < 50) {
    setTimeout(function() { waitForMermaid(callback, attempts + 1); }, 100);
  }
}

// Initial render
waitForMermaid(renderMermaid);

// Re-render on Material SPA page switch
document$.subscribe(function() {
  waitForMermaid(renderMermaid);
});

// Re-render on color scheme toggle
var schemeObserver = new MutationObserver(function() {
  // Reset all processed diagrams so they get re-rendered with new theme
  document.querySelectorAll('.mermaid[data-processed]').forEach(function(el) {
    el.removeAttribute('data-processed');
  });
  waitForMermaid(renderMermaid);
});

document.querySelectorAll('[data-md-color-scheme]').forEach(function(el) {
  schemeObserver.observe(el, { attributes: true, attributeFilter: ['data-md-color-scheme'] });
});
