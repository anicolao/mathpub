document.getElementById('publishing-tools').onclick = () => {
  const dialog = document.getElementById('publishing-dialog');
  const frame = document.getElementById('publishing-frame');
  if (!frame.src) frame.src = './publishing.html';
  dialog.showModal();
};
document.getElementById('publishing-close').onclick = () => document.getElementById('publishing-dialog').close();
