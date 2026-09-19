const $ = id => document.getElementById(id);
let plan = null;
async function request(payload) {
  $('status').textContent = 'Working…';
  const response = await fetch('/api/tools', {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Mathpub-Publishing': '1'},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  $('status').textContent = JSON.stringify(data, null, 2);
  if (!response.ok) throw new Error(data.error || 'Publishing operation failed');
  return data;
}
function handle(fn) {
  return async event => {
    event?.preventDefault();
    try { await fn(); } catch (error) { $('status').textContent += '\n' + error.message; }
  };
}
function showPlan(value) {
  plan = value;
  $('plan-preview').textContent = JSON.stringify(plan, null, 2);
  $('confirm').disabled = false; $('confirm').checked = false; $('upload').disabled = true;
}
$('review-form').onsubmit = handle(async () => {
  const result = await request({action:'review',before:$('before').value,after:$('after').value,output:$('review-output').value});
  $('review-view').src = result.url; $('review-view').hidden = false;
});
$('login').onclick = handle(() => request({action:'kdp-login',config:$('config').value}));
$('plan-form').onsubmit = handle(async () => showPlan(await request({action:'kdp-plan',
  release:$('release').value,book:$('book').value,config:$('config').value,output:$('plan').value})));
$('load-plan').onclick = handle(async () => showPlan(await request({action:'kdp-load-plan',plan:$('plan').value})));
$('confirm').onchange = () => { $('upload').disabled = !plan || !$('confirm').checked; };
$('plan').oninput = () => { plan=null; $('confirm').checked=false; $('confirm').disabled=true; $('upload').disabled=true; };
$('upload').onclick = handle(async () => {
  if (!plan || !$('confirm').checked) return;
  $('upload').disabled=true;
  try { await request({action:'kdp-upload',plan:$('plan').value,output:$('attempt').value,
    confirmation:plan.sha256,resume:$('resume').checked,retry_uncertain:$('retry').checked}); }
  finally { $('confirm').checked=false; }
});
