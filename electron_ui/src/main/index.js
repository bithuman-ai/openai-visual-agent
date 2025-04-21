const { app, BrowserWindow } = require('electron');
const WindowManager = require('./core/window-manager');
const AppController = require('./core/app-controller');

// Initialize window manager and app controller
const windowManager = new WindowManager();
const appController = new AppController(windowManager);

// When Electron has finished initialization
app.whenReady().then(() => {
  // Create main window
  appController.createMainWindow();
  
  // Create application menu
  appController.createMenu();
  
  // Initialize the app
  appController.init();
});

// Quit when all windows are closed, except on macOS
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// On macOS it's common to re-create a window when the dock icon is clicked
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    appController.createMainWindow();
  }
}); 