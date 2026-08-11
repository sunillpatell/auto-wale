const cursor = document.querySelector('.cursor');
window.addEventListener('mousemove', e => {
  cursor.style.left = e.clientX + 'px';
  cursor.style.top = e.clientY + 'px';
});
document.querySelectorAll('a,button').forEach(el => {
  el.addEventListener('mouseenter', () => { cursor.style.width='32px'; cursor.style.height='32px'; cursor.style.background='#fff'; });
  el.addEventListener('mouseleave', () => { cursor.style.width='14px'; cursor.style.height='14px'; cursor.style.background='transparent'; });
});

// Tiny reveal-on-scroll interaction
const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if(entry.isIntersecting) entry.target.classList.add('in');
  });
}, {threshold:.12});
document.querySelectorAll('.statement h2,.project,.contact h2,.email').forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(35px)';
  el.style.transition = 'opacity .8s ease, transform .8s ease';
  observer.observe(el);
});
const style = document.createElement('style');
style.textContent = '.in{opacity:1!important;transform:none!important}';
document.head.appendChild(style);
