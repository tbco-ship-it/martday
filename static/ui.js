// Scroll reveal for below-the-fold sections: one short rise, once, skipped under reduced motion.
(function () {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  const targets = document.querySelectorAll('main > section:not(:first-of-type), main > .grid2, main > h2, main > .tbl, main > .prose, main > .sec, main > .sheet:not(:first-of-type)');
  const io = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });
  targets.forEach(t => { if (t.getBoundingClientRect().top > innerHeight) { t.classList.add('reveal'); io.observe(t); } });
})();
