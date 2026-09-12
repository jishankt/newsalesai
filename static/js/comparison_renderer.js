/**
 * Universal Comparison Renderer for Kepler Tech SalesAI.
 * Renders structured comparison_data JSON as:
 *   - Desktop (>= 640px): responsive <table>
 *   - Mobile  (<  640px): stacked per-product cards
 *
 * Security: all values are set via textContent (never innerHTML with data).
 * No Markdown table is ever injected into the DOM.
 */

(function (global) {
  'use strict';

  const HIGHLIGHT_BG = '#fffbeb';   // amber-50
  const HIGHLIGHT_BORDER = '#f59e0b'; // amber-500
  const NOT_VERIFIED = 'Not verified in the approved catalogue.';
  const PLACEHOLDER = '/static/images/printer-placeholder.svg';

  /**
   * Render a comparison_data JSON object into targetEl.
   * @param {Object} data  - comparison_data from /api/chat response
   * @param {Element} targetEl - DOM element to append the comparison into
   */
  function renderComparison(data, targetEl) {
    if (!data || !data.products || data.products.length < 2 || !data.criteria) return;

    const wrap = document.createElement('div');
    wrap.className = 'comparison-wrap';

    // Cross-category note (if present)
    if (data.cross_category_note) {
      const note = document.createElement('div');
      note.className = 'comparison-cross-note';
      note.textContent = data.cross_category_note;
      wrap.appendChild(note);
    }

    const isMobile = window.matchMedia && window.matchMedia('(max-width: 640px)').matches;

    if (isMobile) {
      _renderMobileCards(wrap, data);
    } else {
      _renderDesktopTable(wrap, data);
    }

    // Re-render on window resize (debounced)
    let resizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        const nowMobile = window.matchMedia('(max-width: 640px)').matches;
        if (nowMobile !== isMobile) {
          wrap.innerHTML = '';
          if (data.cross_category_note) {
            const note = document.createElement('div');
            note.className = 'comparison-cross-note';
            note.textContent = data.cross_category_note;
            wrap.appendChild(note);
          }
          nowMobile ? _renderMobileCards(wrap, data) : _renderDesktopTable(wrap, data);
        }
      }, 200);
    });

    targetEl.appendChild(wrap);
  }

  // ── Desktop: <table> ───────────────────────────────────────────────────

  function _renderDesktopTable(wrap, data) {
    const products = data.products;

    const tableWrap = document.createElement('div');
    tableWrap.className = 'comparison-table-wrap';

    const table = document.createElement('table');
    table.className = 'comparison-table';

    // === THEAD: product images + names ===
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');

    // Empty corner cell
    const cornerTh = document.createElement('th');
    cornerTh.className = 'comparison-th comparison-corner';
    headRow.appendChild(cornerTh);

    products.forEach(function (prod) {
      const th = document.createElement('th');
      th.className = 'comparison-th comparison-product-header';

      // Image
      const imgLink = document.createElement('a');
      imgLink.href = prod.product_url || 'https://www.keplertechllc.com/';
      imgLink.target = '_blank';
      imgLink.rel = 'noopener noreferrer';

      const img = document.createElement('img');
      img.src = prod.image_url || PLACEHOLDER;
      img.alt = prod.display_name;
      img.className = 'comparison-product-img';
      img.onerror = function () { this.src = PLACEHOLDER; };
      imgLink.appendChild(img);
      th.appendChild(imgLink);

      // Name
      const nameEl = document.createElement('div');
      nameEl.className = 'comparison-product-name';
      nameEl.textContent = prod.display_name;
      th.appendChild(nameEl);

      // "View Details" link
      const viewLink = document.createElement('a');
      viewLink.href = prod.product_url || 'https://www.keplertechllc.com/';
      viewLink.target = '_blank';
      viewLink.rel = 'noopener noreferrer';
      viewLink.className = 'comparison-view-link';
      viewLink.textContent = 'View Details \u2197';
      th.appendChild(viewLink);

      headRow.appendChild(th);
    });

    thead.appendChild(headRow);
    table.appendChild(thead);

    // === TBODY: one row per criterion ===
    const tbody = document.createElement('tbody');

    data.criteria.forEach(function (row) {
      const tr = document.createElement('tr');
      tr.className = row.highlight ? 'comparison-row comparison-row-diff' : 'comparison-row';

      // Label cell
      const labelTd = document.createElement('td');
      labelTd.className = 'comparison-label';
      labelTd.textContent = row.label;
      tr.appendChild(labelTd);

      // Value cell for each product
      products.forEach(function (prod) {
        const td = document.createElement('td');
        td.className = 'comparison-value';
        if (row.highlight) {
          td.className += ' comparison-value-diff';
        }
        const val = (row.values && row.values[prod.id]) || NOT_VERIFIED;
        td.textContent = val;
        if (val === NOT_VERIFIED) {
          td.classList.add('comparison-not-verified');
        }
        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);
  }

  // ── Mobile: stacked product cards ─────────────────────────────────────

  function _renderMobileCards(wrap, data) {
    const products = data.products;
    const criteria = data.criteria;

    const container = document.createElement('div');
    container.className = 'comparison-mobile-cards';

    products.forEach(function (prod) {
      const card = document.createElement('div');
      card.className = 'comparison-mobile-card';

      // Product header
      const header = document.createElement('div');
      header.className = 'comparison-mobile-header';

      const img = document.createElement('img');
      img.src = prod.image_url || PLACEHOLDER;
      img.alt = prod.display_name;
      img.className = 'comparison-mobile-img';
      img.onerror = function () { this.src = PLACEHOLDER; };
      header.appendChild(img);

      const nameEl = document.createElement('div');
      nameEl.className = 'comparison-mobile-name';
      nameEl.textContent = prod.display_name;
      header.appendChild(nameEl);

      const viewLink = document.createElement('a');
      viewLink.href = prod.product_url || 'https://www.keplertechllc.com/';
      viewLink.target = '_blank';
      viewLink.rel = 'noopener noreferrer';
      viewLink.className = 'comparison-view-link';
      viewLink.textContent = 'View Details \u2197';
      header.appendChild(viewLink);

      card.appendChild(header);

      // Criteria rows
      const dl = document.createElement('dl');
      dl.className = 'comparison-mobile-dl';

      criteria.forEach(function (row) {
        if (row.key === 'model') return; // already in header

        const dt = document.createElement('dt');
        dt.className = 'comparison-mobile-dt';
        dt.textContent = row.label;

        const dd = document.createElement('dd');
        dd.className = row.highlight
          ? 'comparison-mobile-dd comparison-mobile-dd-diff'
          : 'comparison-mobile-dd';

        const val = (row.values && row.values[prod.id]) || NOT_VERIFIED;
        dd.textContent = val;
        if (val === NOT_VERIFIED) {
          dd.classList.add('comparison-not-verified');
        }

        dl.appendChild(dt);
        dl.appendChild(dd);
      });

      card.appendChild(dl);
      container.appendChild(card);
    });

    wrap.appendChild(container);
  }

  // Expose globally
  global.renderComparison = renderComparison;

})(window);
