// This is the main entry point for the Electron app
const { app, BrowserWindow } = require('electron');
const WindowManager = require('./src/main/core/window-manager');
const AppController = require('./src/main/core/app-controller');
const logger = require('./src/main/utils/logger');
const { exec } = require('child_process');
const { displayShortcuts } = require('./src/main/utils/shortcut-display');

// Suppress macOS-specific warnings about NSOpenPanel method identifier
// This needs to be done before initializing Electron
const originalStderrWrite = process.stderr.write;
process.stderr.write = function(data) {
  // Filter out the NSOpenPanel warning
  if (typeof data === 'string' && 
      data.includes('NSOpenPanel') && 
      data.includes('overrides the method identifier')) {
    return true;
  }
  return originalStderrWrite.apply(process.stderr, arguments);
};

// Set the app name to match the Python code
app.setName('bitHumanVisualAgent');
logger.system('Starting bitHuman Visual Agent Electron UI');

// Display keyboard shortcuts in terminal
displayShortcuts();

// Log color mode
if (process.env.NO_COLOR !== undefined) {
  logger.system('Running in NO_COLOR mode - log colors disabled');
} else if (process.env.FORCE_COLOR !== undefined) {
  logger.system(`Running with FORCE_COLOR=${process.env.FORCE_COLOR} - log colors enforced`);
}

// Initialize window manager and app controller
const windowManager = new WindowManager();
const appController = new AppController(windowManager);

// When Electron has finished initialization
app.whenReady().then(() => {
  logger.electron('Electron app is ready');
  
  // Create main window
  appController.createMainWindow();
  logger.ui('Main window created');
  
  // Create application menu
  appController.createMenu();
  logger.ui('Application menu created');
  
  // Initialize the app
  appController.init();
  logger.system('Application initialized');
});

// Quit when all windows are closed, except on macOS
app.on('window-all-closed', () => {
  logger.electron('All windows closed');
  if (process.platform !== 'darwin') {
    logger.system('Quitting application');
    app.quit();
  }
});

// On macOS it's common to re-create a window when the dock icon is clicked
app.on('activate', () => {
  logger.electron('App activated');
  if (BrowserWindow.getAllWindows().length === 0) {
    logger.ui('Recreating main window');
    appController.createMainWindow();
  }
}); 

// Add a 'before-quit' event handler to kill the tmux session
app.on('before-quit', () => {
  logger.system('Killing tmux session before quitting...');
  exec('tmux kill-session -t desktop-agent', (error, stdout, stderr) => {
    if (error) {
      logger.system(`Error killing tmux session: ${error.message}`);
      return;
    }
    if (stderr) {
      logger.system(`tmux stderr: ${stderr}`);
      return;
    }
    logger.system('Successfully killed tmux session');
  });
}); 