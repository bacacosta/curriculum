// Align the decorative ruler shading and tick origins with the paper.
const documentPage = document.querySelector('.document-page');
const horizontalRuler = document.querySelector('.horizontal-ruler');
const verticalRuler = document.querySelector('.vertical-ruler');
let rulerUpdatePending = false;

function rulerImage(extent, start, vertical) {
  const width = vertical ? 26 : extent;
  const height = vertical ? extent : 26;
  const marks = [];

  function segment(origin, direction, low, high) {
    const stepSize = 9.45;
    const first = Math.max(0, Math.ceil((direction > 0 ? low - origin : origin - high) / stepSize));
    const last = Math.floor((direction > 0 ? high - origin : origin - low) / stepSize);
    for (let step = first; step <= last; step++) {
      const point = (origin + direction * step * stepSize).toFixed(2);
      const major = step % 4 === 0;
      const length = step === 0 ? 10 : major ? 7 : step % 2 === 0 ? 5 : 3;
      const path = vertical ? `M${26 - length} ${point}H26` : `M${point} ${26 - length}V26`;
      marks.push(`<path d="${path}" stroke="#808080" stroke-width=".7"/>`);
      if (major && (step || direction > 0)) {
        const position = vertical ? `x="10" y="${point}" dominant-baseline="central"` :
          `x="${point}" y="12"`;
        marks.push(
          `<text ${position} text-anchor="middle" font-family="Arial,sans-serif" font-size="9" fill="#646464">${step / 4}</text>`
          );
      }
    }
  }
  // Before the page, count outward; after its start, keep counting forward.
  segment(start, -1, 0, Math.min(extent, start));
  segment(start, 1, Math.max(0, start), extent);
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#f8f8f8"/>${marks.join('')}</svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

function alignRulers() {
  const page = documentPage.getBoundingClientRect();
  const horizontal = horizontalRuler.getBoundingClientRect();
  const vertical = verticalRuler.getBoundingClientRect();
  horizontalRuler.style.setProperty('--page-start', `${page.left - horizontal.left}px`);
  horizontalRuler.style.setProperty('--page-end', `${page.right - horizontal.left}px`);
  verticalRuler.style.setProperty('--page-start', `${page.top - vertical.top}px`);
  verticalRuler.style.setProperty('--page-end', `${page.bottom - vertical.top}px`);
  horizontalRuler.style.setProperty('--ruler-image', rulerImage(horizontal.width,
    page.left - horizontal.left, false));
  verticalRuler.style.setProperty('--ruler-image', rulerImage(vertical.height,
    page.top - vertical.top, true));
  rulerUpdatePending = false;
}

function scheduleRulerUpdate() {
  if (rulerUpdatePending) return;
  rulerUpdatePending = true;
  requestAnimationFrame(alignRulers);
}

if (documentPage && horizontalRuler && verticalRuler) {
  alignRulers();
  new ResizeObserver(scheduleRulerUpdate).observe(documentPage);
  window.addEventListener('resize', scheduleRulerUpdate);
  window.addEventListener('scroll', scheduleRulerUpdate, {
    passive: true
  });
}
