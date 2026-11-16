(() => {
  'use strict';
  const byId = (id) => document.getElementById(id);
  const navLinks = [...document.querySelectorAll('.sidebar nav a')];
  const sections = [...document.querySelectorAll('main section[id]')];
  const updateReading = () => {
    const max = document.documentElement.scrollHeight - innerHeight;
    byId('reading-progress').style.width = `${max > 0 ? Math.min(100, scrollY / max * 100) : 0}%`;
    const active = [...sections].reverse().find((section) => section.getBoundingClientRect().top < 180) || sections[0];
    navLinks.forEach((link) => {
      const selected = link.hash === `#${active.id}`;
      link.classList.toggle('active', selected);
      if (selected) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  };
  addEventListener('scroll', updateReading, { passive: true });
  addEventListener('resize', updateReading);
  updateReading();
  byId('print-guide').addEventListener('click', () => window.print());

  const dialog = byId('image-dialog');
  document.querySelectorAll('[data-zoom]').forEach((button) => {
    button.addEventListener('click', () => {
      const img = button.querySelector('img');
      byId('zoom-image').src = img.currentSrc || img.src;
      byId('zoom-image').alt = img.alt;
      byId('zoom-caption').textContent = button.closest('figure').querySelector('figcaption').textContent;
      dialog.showModal();
    });
  });
  byId('close-image').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });

  const rows = [...document.querySelectorAll('#field-table tbody tr')];
  const filterFields = () => {
    const query = byId('field-search').value.trim().toLocaleLowerCase('ar');
    let count = 0;
    rows.forEach((row) => {
      const matches = row.textContent.toLocaleLowerCase('ar').includes(query);
      row.hidden = !matches;
      if (matches) count += 1;
    });
    byId('field-count').textContent = `${count.toLocaleString('ar-EG')} من ${rows.length.toLocaleString('ar-EG')} حقل أو مجموعة حقول`;
  };
  byId('field-search').addEventListener('input', filterFields);
  filterFields();

  const calculate = () => {
    const [length, width, filmWidth, rollLength] = ['calc-length', 'calc-width', 'calc-film', 'calc-roll'].map((id) => Number(byId(id).value));
    const valid = [length, width, filmWidth, rollLength].every(Number.isFinite) && length >= 0 && width >= 0 && filmWidth > 0 && rollLength > 0;
    if (!valid) {
      byId('calc-quantity').textContent = '—';
      byId('calc-details').textContent = '';
      byId('calc-message').textContent = 'اكتب أرقام صحيحة؛ عرض الفيلم وطول الرول لازم يبقوا أكبر من صفر.';
      return;
    }
    const raw = length * width * .0254 / (filmWidth * rollLength);
    const rounded = Math.ceil(raw * 100 - 1e-9) / 100;
    byId('calc-quantity').textContent = rounded.toFixed(2);
    byId('calc-details').textContent = `قبل التقريب: ${raw.toFixed(6)} رول · مساحة القصّة: ${(length * width * .0254 ** 2).toFixed(4)} م²`;
    const messages = [];
    if (width > filmWidth) messages.push('في أودو المقاس ده بيتمنع، لأن عرض القصّة أكبر من عرض الفيلم.');
    if (length > 20 || width > 25) messages.push('بالمقارنة بقياسي المثال 15 × 20 وسماح 5 إنش، فيه زيادة تستحق تنبيه.');
    if (!messages.length) messages.push('المقاسات جوه سماح الجزء في مثال Small. إجمالي الخدمة بيتراجع لوحده.');
    byId('calc-message').textContent = messages.join(' ');
  };
  document.querySelectorAll('.calc-inputs input').forEach((input) => input.addEventListener('input', calculate));
  calculate();
})();

// Jump to the matching explanation without forcing playback.
document.querySelectorAll('[data-video-seek]').forEach((button) => {
  button.addEventListener('click', () => {
    const video = button.dataset.videoTarget ? document.getElementById(button.dataset.videoTarget) : document.querySelector('#video video');
    const seconds = Number(button.dataset.videoSeek);
    if (!video || !Number.isFinite(seconds)) return;
    const seek = () => { video.currentTime = Math.min(seconds, video.duration || seconds); };
    if (video.readyState) seek();
    else video.addEventListener('loadedmetadata', seek, { once: true });
    (button.dataset.videoTarget ? document.getElementById('operations-video') : document.getElementById('video')).scrollIntoView({ behavior: 'smooth', block: 'start' });
    video.focus({ preventScroll: true });
  });
});
