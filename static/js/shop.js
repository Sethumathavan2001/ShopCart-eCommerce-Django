/* ShopCart front-end helpers */
(function () {
  'use strict';

  function getCookie(name) {
    const match = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
    return match ? decodeURIComponent(match.substring(name.length + 1)) : null;
  }

  function csrfToken() {
    const input = document.querySelector('[name="csrfmiddlewaretoken"]');
    return getCookie('csrftoken') || (input && input.value) || '';
  }

  const ICONS = { success: 'bi-check-circle-fill', danger: 'bi-x-circle-fill', error: 'bi-x-circle-fill',
                  warning: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill' };

  function toast(message, type) {
    type = type || 'info';
    let stack = document.querySelector('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      document.body.appendChild(stack);
    }
    const el = document.createElement('div');
    el.className = 'sc-toast ' + type;
    el.setAttribute('role', 'status');
    const icon = document.createElement('i');
    icon.className = 'bi ' + (ICONS[type] || ICONS.info);
    const text = document.createElement('div');
    text.textContent = message;
    const close = document.createElement('button');
    close.className = 'close';
    close.setAttribute('aria-label', 'Close');
    close.innerHTML = '<i class="bi bi-x-lg" style="font-size:.8rem"></i>';
    el.append(icon, text, close);
    stack.appendChild(el);
    const dismiss = () => { el.classList.add('hide'); setTimeout(() => el.remove(), 250); };
    close.addEventListener('click', dismiss);
    setTimeout(dismiss, 4000);
  }

  async function postJSON(url, data) {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify(data || {}),
    });
    let body = {};
    try { body = await res.json(); } catch (e) { /* non-JSON response */ }
    if (res.status === 401 || body.login_required) {
      window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname + window.location.search);
      throw new Error('login required');
    }
    return { ok: res.ok, data: body };
  }

  function setCount(selector, n) {
    document.querySelectorAll(selector).forEach(el => {
      el.textContent = n > 0 ? n : '';
      el.dataset.count = n;
    });
  }

  function money(v) {
    const n = Number(v);
    return 'Rs. ' + n.toLocaleString('en-IN', { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 });
  }

  // ---------------------------------------------------------------- add to cart
  document.addEventListener('click', async function (e) {
    const btn = e.target.closest('[data-add-cart]');
    if (!btn) return;
    e.preventDefault();
    const qtyInput = btn.dataset.qtyInput ? document.querySelector(btn.dataset.qtyInput) : null;
    const qty = qtyInput ? parseInt(qtyInput.value, 10) || 1 : 1;
    btn.disabled = true;
    const original = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    try {
      const { ok, data } = await postJSON('/addtocart', { pid: btn.dataset.addCart, product_q: qty });
      toast(data.status || 'Something went wrong', ok ? 'success' : 'danger');
      if (ok) {
        setCount('[data-cart-count]', data.cart_count);
        btn.innerHTML = '<i class="bi bi-check2"></i> Added';
        setTimeout(() => { btn.innerHTML = original; btn.disabled = false; }, 1400);
        return;
      }
    } catch (err) { /* redirected to login */ }
    btn.innerHTML = original;
    btn.disabled = false;
  });

  // ---------------------------------------------------------------- wishlist toggle
  document.addEventListener('click', async function (e) {
    const btn = e.target.closest('[data-wish]');
    if (!btn) return;
    e.preventDefault();
    try {
      const { ok, data } = await postJSON('/addtofav', { pid: btn.dataset.wish });
      if (!ok) { toast(data.status || 'Something went wrong', 'danger'); return; }
      document.querySelectorAll('[data-wish="' + btn.dataset.wish + '"]').forEach(b => {
        b.classList.toggle('active', data.in_wishlist);
        const label = b.querySelector('[data-wish-label]');
        if (label) label.textContent = data.in_wishlist ? 'Wishlisted' : 'Add to Wishlist';
      });
      setCount('[data-wish-count]', data.wishlist_count);
      toast(data.status, data.in_wishlist ? 'success' : 'info');
    } catch (err) { /* redirected to login */ }
  });

  // ---------------------------------------------------------------- quantity steppers
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-qty-step]');
    if (!btn) return;
    const wrap = btn.closest('.qty-input');
    const input = wrap.querySelector('input');
    const min = parseInt(input.min || '1', 10);
    const max = parseInt(input.max || '99', 10);
    let v = (parseInt(input.value, 10) || min) + parseInt(btn.dataset.qtyStep, 10);
    v = Math.max(min, Math.min(max, v));
    if (String(v) !== input.value) {
      input.value = v;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });

  // ---------------------------------------------------------------- cart page live update
  document.addEventListener('change', async function (e) {
    const input = e.target.closest('[data-cart-qty]');
    if (!input) return;
    const row = input.closest('[data-cart-row]');
    row.style.opacity = '.5';
    try {
      const { ok, data } = await postJSON('/cart/update/' + input.dataset.cartQty, { quantity: input.value });
      if (!ok) { toast(data.message || 'Could not update cart', 'danger'); return; }
      if (data.empty) { window.location.reload(); return; }
      if (data.removed) { row.remove(); } else {
        input.value = data.quantity;
        row.querySelector('[data-line-total]').textContent = money(data.line_total);
      }
      setCount('[data-cart-count]', data.cart_count);
      const set = (k, v) => document.querySelectorAll('[data-sum="' + k + '"]').forEach(el => { el.textContent = v; });
      set('items', data.cart_count);
      set('mrp', money(data.mrp_total));
      set('savings', '- ' + money(data.product_savings));
      set('coupon', '- ' + money(data.coupon_discount));
      set('subtotal', money(data.subtotal));
      set('shipping', Number(data.shipping) > 0 ? money(data.shipping) : 'FREE');
      set('total', money(data.total));
      const gap = Number(data.free_shipping_gap);
      const shipMsg = document.querySelector('[data-ship-msg]');
      if (shipMsg) {
        shipMsg.innerHTML = gap > 0
          ? 'Add <strong>' + money(gap) + '</strong> more for <strong>FREE delivery</strong>'
          : '<i class="bi bi-truck text-success"></i> Yay! Your order qualifies for <strong>FREE delivery</strong>';
        const bar = document.querySelector('[data-ship-bar]');
        if (bar) {
          const threshold = Number(bar.dataset.threshold);
          bar.style.width = Math.min(100, (Number(data.subtotal) / threshold) * 100) + '%';
        }
      }
    } catch (err) { /* ignore */ } finally { row.style.opacity = ''; }
  });

  // ---------------------------------------------------------------- live search suggestions
  document.querySelectorAll('[data-search]').forEach(function (form) {
    const input = form.querySelector('input[name="q"]');
    const box = form.querySelector('.search-suggest');
    let timer, active = -1;

    function render(results, q) {
      box.innerHTML = '';
      active = -1;
      if (!results.length) {
        box.innerHTML = '<div class="p-3 small text-muted">No products match "<strong></strong>"</div>';
        box.querySelector('strong').textContent = q;
      }
      results.forEach(r => {
        const a = document.createElement('a');
        a.href = r.url;
        const img = document.createElement('img');
        img.src = r.image; img.alt = '';
        const info = document.createElement('div');
        info.innerHTML = '<div class="s-name"></div><div class="s-meta"></div>';
        info.querySelector('.s-name').textContent = r.name;
        info.querySelector('.s-meta').textContent = r.category + ' · ' + money(r.price);
        a.append(img, info);
        box.appendChild(a);
      });
      const all = document.createElement('a');
      all.href = '/shop?q=' + encodeURIComponent(q);
      all.className = 'justify-content-center small fw-semibold text-primary border-top';
      all.textContent = 'See all results for "' + q + '"';
      box.appendChild(all);
      box.classList.add('show');
    }

    input.addEventListener('input', function () {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) { box.classList.remove('show'); return; }
      timer = setTimeout(async () => {
        const res = await fetch('/search/suggest?q=' + encodeURIComponent(q));
        const data = await res.json();
        if (input.value.trim() === q) render(data.results, q);
      }, 200);
    });
    input.addEventListener('keydown', function (e) {
      const items = box.querySelectorAll('a');
      if (!box.classList.contains('show') || !items.length) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        active = (active + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items.forEach((it, i) => it.classList.toggle('active', i === active));
      } else if (e.key === 'Enter' && active >= 0) {
        e.preventDefault();
        window.location.href = items[active].href;
      } else if (e.key === 'Escape') {
        box.classList.remove('show');
      }
    });
    document.addEventListener('click', function (e) {
      if (!form.contains(e.target)) box.classList.remove('show');
    });
  });

  // ---------------------------------------------------------------- confirm dialogs
  document.addEventListener('submit', function (e) {
    const msg = e.target.dataset.confirm;
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // ---------------------------------------------------------------- back to top
  const topBtn = document.querySelector('.back-to-top');
  if (topBtn) {
    window.addEventListener('scroll', () => topBtn.classList.toggle('show', window.scrollY > 600), { passive: true });
    topBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  }

  // ---------------------------------------------------------------- image zoom on product page
  const zoom = document.querySelector('[data-zoom]');
  if (zoom) {
    const img = zoom.querySelector('img');
    zoom.addEventListener('mousemove', e => {
      const r = zoom.getBoundingClientRect();
      img.style.transformOrigin = ((e.clientX - r.left) / r.width * 100) + '% ' + ((e.clientY - r.top) / r.height * 100) + '%';
      img.style.transform = 'scale(1.8)';
    });
    zoom.addEventListener('mouseleave', () => { img.style.transform = ''; });
  }

  // ---------------------------------------------------------------- server messages -> toasts
  document.querySelectorAll('[data-flash]').forEach(el => {
    toast(el.dataset.flash, el.dataset.level || 'info');
    el.remove();
  });

  window.ShopCart = { toast, postJSON, getCookie, money };
})();
