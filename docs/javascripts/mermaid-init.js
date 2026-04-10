// Initialize Mermaid with dark/light mode support for Material for MkDocs
function initMermaid() {
  var isDark = document.body.getAttribute('data-md-color-scheme') === 'slate'
    || document.documentElement.getAttribute('data-md-color-scheme') === 'slate'
    || document.querySelector('[data-md-color-scheme="slate"]') !== null;

  mermaid.initialize({
    startOnLoad: false,
    theme: isDark ? 'dark' : 'default',
    securityLevel: 'loose',
    themeVariables: isDark ? {
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
    }
  });

  // Material renders mermaid as <pre class="mermaid"><code>...</code></pre>
  // Convert to <div class="mermaid"> so Mermaid v11 can process them
  document.querySelectorAll('pre.mermaid code, pre.mermaid').forEach(function(el) {
    var src = el.tagName === 'CODE' ? el.innerText : el.innerText;
    var pre = el.closest('pre') || el;
    if (pre.getAttribute('data-mermaid-done')) return;
    pre.setAttribute('data-mermaid-done', '1');
    var div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = src;
    pre.parentNode.replaceChild(div, pre);
  });

  mermaid.run({ querySelector: '.mermaid' });
}

// Run after DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMermaid);
} else {
  initMermaid();
}

// Re-run on Material page navigation (SPA)
document.addEventListener('DOMContentSwitch', initMermaid);

// Re-run on color scheme toggle
var observer = new MutationObserver(function(mutations) {
  mutations.forEach(function(m) {
    if (m.attributeName === 'data-md-color-scheme') initMermaid();
  });
});
var targets = document.querySelectorAll('[data-md-color-scheme]');
targets.forEach(function(t) { observer.observe(t, { attributes: true }); });
// Also observe body for scheme changes
observer.observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });
