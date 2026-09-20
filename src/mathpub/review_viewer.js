const $ = id => document.getElementById(id);
const read = name => {try {return localStorage.getItem(name)} catch (_) {return null}};
const save = (name, value) => {try {localStorage.setItem(name, value)} catch (_) {}};
let done = {};
try {const value = JSON.parse(read(key) || '{}');
  if (value && typeof value === 'object' && !Array.isArray(value)) done = value;
} catch (_) {}
const cards = [...document.querySelectorAll('section')];
let visible = [], index = 0;
const reviewed = card => card.querySelector('[data-id]').checked;
function show(scroll = false) {
  index = Math.max(0, Math.min(index, visible.length - 1));
  $('page').value = String(index);
  $('page').disabled = !visible.length;
  $('prev').disabled = !visible.length || index === 0;
  $('next').disabled = !visible.length || index === visible.length - 1;
  $('count').textContent = visible.length
    ? `${index + 1} / ${visible.length} · ${visible.filter(reviewed).length} reviewed in selection · ${cards.filter(reviewed).length} / ${cards.length} overall`
    : 'No matching pages';
  if (scroll) visible[index]?.scrollIntoView({block:'start'});
}
function filter() {
  const current = visible[index];
  cards.forEach(card => {card.hidden =
    ($('book').value !== '' && card.dataset.book !== $('book').value) ||
    ($('changed').checked && card.dataset.status === 'unchanged') ||
    !card.dataset.text.includes($('filter').value.toLowerCase());
  });
  visible = cards.filter(card => !card.hidden);
  $('page').replaceChildren(...visible.map((card, i) =>
    new Option(`${i + 1}: ${card.dataset.description} · ${card.dataset.status}`, i)));
  index = Math.max(0, visible.indexOf(current));
  show();
}
document.querySelectorAll('[data-id]').forEach(input => {
  input.checked = done[input.dataset.id] === true;
  input.onchange = () => {done[input.dataset.id] = input.checked;
    save(key, JSON.stringify(done)); show();};
});
$('filter').oninput = filter; $('changed').onchange = filter; $('book').onchange = filter;
$('page').onchange = () => {index = Number($('page').value); show(true)};
$('prev').onclick = () => {index--; show(true)};
$('next').onclick = () => {index++; show(true)};
document.onkeydown = e => {
  if (e.target.matches('input,select,textarea') || e.target.isContentEditable) return;
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    e.preventDefault(); index += e.key === 'ArrowLeft' ? -1 : 1; show(true);
  }
};
const zoomKey = 'mathpub-review-zoom';
$('zoom').replaceChildren(...Array.from({length:20}, (_, i) => new Option(`${(i+1)*10}%`, (i+1)*10)));
function zoom(value) {
  let n = Number(value);
  if (!Number.isInteger(n) || n < 10 || n > 200 || n % 10) n = 100;
  $('zoom').value = String(n); document.documentElement.style.setProperty('--zoom', n / 100);
}
zoom(read(zoomKey));
$('zoom').onchange = () => {zoom($('zoom').value); save(zoomKey, $('zoom').value)};
document.querySelectorAll('img').forEach(img => img.onclick = () => {
  zoom(Number($('zoom').value) === 200 ? 100 : 200); save(zoomKey, $('zoom').value);
});
$('export').onclick = () => {
  const a = document.createElement('a');
  const url = URL.createObjectURL(new Blob([JSON.stringify({key, done})], {type:'application/json'}));
  a.href = url; a.download = 'review-progress.json'; a.click(); URL.revokeObjectURL(url);
};
filter();
