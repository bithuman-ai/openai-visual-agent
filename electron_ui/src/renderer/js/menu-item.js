require('electron').ipcRenderer.on('set-content', (event, content) => {
    document.getElementById('menu-image').src = content.imagePath;
    document.getElementById('menu-label').textContent = content.label;
});

document.querySelector('.menu-item').addEventListener('click', () => {
    require('electron').ipcRenderer.send('menu-item-clicked');
}); 