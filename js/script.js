(function () {
  'use strict';

  document.getElementById('year').textContent = new Date().getFullYear();

  /* ---- Smooth scroll for data-scroll buttons ---- */
  document.querySelectorAll('[data-scroll]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var target = document.querySelector(btn.getAttribute('data-scroll'));
      if (!target) return;
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      closeMenu();
    });
  });

  /* ---- Mobile nav toggle ---- */
  var navToggle = document.getElementById('nav-toggle');
  var mainNav = document.getElementById('main-nav');

  function closeMenu() {
    navToggle.classList.remove('open');
    mainNav.classList.remove('open');
    navToggle.setAttribute('aria-expanded', 'false');
  }

  navToggle.addEventListener('click', function () {
    var isOpen = mainNav.classList.toggle('open');
    navToggle.classList.toggle('open', isOpen);
    navToggle.setAttribute('aria-expanded', String(isOpen));
  });

  document.addEventListener('click', function (e) {
    if (!mainNav.classList.contains('open')) return;
    if (mainNav.contains(e.target) || navToggle.contains(e.target)) return;
    closeMenu();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeMenu();
  });

  /* ---- FAQ accordion ---- */
  var triggers = document.querySelectorAll('.accordion-trigger');
  triggers.forEach(function (trigger) {
    var panel = trigger.nextElementSibling;
    trigger.addEventListener('click', function () {
      var isOpen = trigger.getAttribute('aria-expanded') === 'true';

      triggers.forEach(function (t) {
        if (t === trigger) return;
        t.setAttribute('aria-expanded', 'false');
        t.nextElementSibling.style.maxHeight = null;
      });

      trigger.setAttribute('aria-expanded', String(!isOpen));
      panel.style.maxHeight = isOpen ? null : panel.scrollHeight + 'px';
    });
  });

  /* ---- Testimonial dots (mobile carousel indicator) ---- */
  var track = document.getElementById('testimonial-track');
  var dotsWrap = document.getElementById('testimonial-dots');
  if (track && dotsWrap) {
    var cards = track.children.length;
    for (var i = 0; i < cards; i++) {
      var dot = document.createElement('span');
      if (i === 0) dot.classList.add('active');
      dotsWrap.appendChild(dot);
    }

    function updateDots() {
      if (getComputedStyle(track).gridTemplateColumns.split(' ').length > 1) return;
    }

    track.addEventListener('scroll', function () {
      var index = Math.round(track.scrollLeft / track.clientWidth);
      Array.prototype.forEach.call(dotsWrap.children, function (d, idx) {
        d.classList.toggle('active', idx === index);
      });
    });
  }

  /* ---- Header shadow on scroll ---- */
  var header = document.getElementById('site-header');
  var lastScrolled = false;
  window.addEventListener('scroll', function () {
    var scrolled = window.scrollY > 8;
    if (scrolled !== lastScrolled) {
      header.style.boxShadow = scrolled ? '0 4px 20px rgba(15,23,42,.06)' : 'none';
      lastScrolled = scrolled;
    }
  });

  /* ---- Contact form (front-end only demo) ---- */
  var form = document.getElementById('contact-form');
  var status = document.getElementById('form-status');

  form.addEventListener('submit', function (e) {
    e.preventDefault();

    var fullname = form.fullname.value.trim();
    var org = form.org.value.trim();
    var phone = form.phone.value.trim();
    var email = form.email.value.trim();
    var emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!fullname || !org || !phone || !email) {
      status.textContent = 'נא למלא את כל שדות החובה.';
      status.className = 'form-status error';
      return;
    }
    if (!emailPattern.test(email)) {
      status.textContent = 'כתובת הדוא"ל שהוזנה אינה תקינה.';
      status.className = 'form-status error';
      return;
    }

    status.textContent = 'תודה! הפנייה התקבלה ונחזור אליכם בהקדם.';
    status.className = 'form-status success';
    form.reset();
  });
})();
