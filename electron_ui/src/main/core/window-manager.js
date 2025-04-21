const { app, BrowserWindow, screen } = require('electron');
const menuUtils = require('../utils/menu-utils');
const path = require('path');
const fs = require('fs');
const { EventEmitter } = require('events');
const logger = require('../utils/logger');
const os = require('os');

/**
 * WindowManager class handles creation and management of application windows
 */
class WindowManager extends EventEmitter {
  constructor() {
    super();
    this.mainWindow = null;
    this.settingsWindow = null;
    this.menuWindows = [];
    this.isMenuVisible = false;
    this.displayMode = 'circle';
    this.previousSize = null;
    this.originalSize = null;
    this.settingsWindowOpenedWith = {};
    this.helpWindow = null;
  }

  /**
   * Get the user data directory
   * @returns {string} - Path to user data directory
   */
  getUserDataDirectory() {
    const appName = 'bitHumanVisualAgent';
    const homedir = os.homedir();
    
    if (process.platform === 'darwin') { // macOS
      return path.join(homedir, 'Library', 'Application Support', appName);
    } else if (process.platform === 'win32') { // Windows
      return path.join(process.env.APPDATA || path.join(homedir, 'AppData', 'Roaming'), appName);
    } else { // Linux and others
      return path.join(homedir, '.local', 'share', appName);
    }
  }

  /**
   * Create the main application window
   * @param {Function} setupContextMenu - Function to set up context menu
   * @param {Function} handleMinimizeShortcut - Function to handle minimize shortcut
   * @param {Function} updateMenuPositions - Function to update menu positions
   * @returns {BrowserWindow} - The created main window
   */
  createMainWindow(setupContextMenu, handleMinimizeShortcut, updateMenuPositions) {
    // Get the primary display's work area
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
    
    // Calculate window size (1/6.67 of screen width)
    const windowSize = Math.floor(screenWidth / 6.67);
    
    // Store the original window size
    this.originalSize = [windowSize, windowSize];
    
    // Calculate position for lower right corner
    const x = screenWidth - windowSize - 50; // 50px margin from right edge
    const y = screenHeight - windowSize - 50; // 50px margin from bottom edge (lifted by 50px)
    
    // Create the browser window
    this.mainWindow = new BrowserWindow({
      width: windowSize,
      height: windowSize,
      x: x,
      y: y,
      frame: false,
      transparent: true,
      resizable: false,
      alwaysOnTop: true,
      backgroundColor: '#00000000',
      webPreferences: {
        nodeIntegration: true,
        contextIsolation: false
      }
    });

    // Explicitly set initial display mode and resizable state
    this.displayMode = 'circle';
    this.mainWindow.setResizable(false);

    // Load the index.html file
    this.mainWindow.loadFile(path.join(__dirname, '../../renderer/html/index.html'));

    // Make window draggable
    this.mainWindow.setMovable(true);

    // Update menu positions when main window moves
    this.mainWindow.on('moved', () => {
      if (this.isMenuVisible) {
        updateMenuPositions();
      }
    });

    // Set up context menu
    setupContextMenu(this.mainWindow);

    // Add keyboard shortcut handler
    handleMinimizeShortcut(this.mainWindow);

    return this.mainWindow;
  }

  /**
   * Create the settings window
   * @param {Function} onClosed - Callback when window is closed
   * @returns {BrowserWindow} - The settings window
   */
  createSettingsWindow(onClosed) {
    // Close all menu windows if they're visible
    if (this.isMenuVisible) {
      this.closeMenuWindows();
    }

    // Store current settings to compare when window is closed
    try {
      const userDataPath = this.getUserDataDirectory();
      const settingsPath = path.join(userDataPath, 'settings.json');
      logger.system('Loading settings from path: ' + settingsPath);
      
      // Store original settings
      if (fs.existsSync(settingsPath)) {
        this.settingsWindowOpenedWith = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
        logger.system("Stored original settings when opening settings window");
      } else {
        logger.system('No settings file found at: ' + settingsPath);
        this.settingsWindowOpenedWith = {};
      }
    } catch (error) {
      logger.error('Error storing original settings: ' + error, logger.LogCategory.SYSTEM);
      this.settingsWindowOpenedWith = {};
    }

    // Hide the main window with fade
    if (this.mainWindow) {
      this.mainWindow.webContents.send('fade-out');
      setTimeout(() => {
        this.mainWindow.hide();
      }, 300); // Match the CSS transition duration
    }

    this.settingsWindow = new BrowserWindow({
      width: 1200,
      height: 800,
      webPreferences: {
        nodeIntegration: true,
        contextIsolation: false
      },
      show: false,
      frame: false,
      titleBarStyle: 'hidden',
      resizable: false,
      minimizable: false,
      maximizable: false,
      closable: false,
      backgroundColor: '#ffffff'
    });

    // Load the settings.html file - no need to pass port as query parameter anymore
    const settingsHtmlPath = path.join(__dirname, '../../renderer/html/settings.html');
    const settingsUrl = `file://${settingsHtmlPath}`;
    this.settingsWindow.loadURL(settingsUrl);

    logger.ui('Opening settings window');

    this.settingsWindow.once('ready-to-show', () => {
      this.settingsWindow.show();
    });

    this.settingsWindow.on('closed', () => {
      this.settingsWindow = null;
      onClosed();
    });

    // Prevent closing by Alt+F4 or other keyboard shortcuts
    this.settingsWindow.on('close', (event) => {
      // Only allow closing through our close-settings-window IPC event
      event.preventDefault();
    });

    return this.settingsWindow;
  }

  /**
   * Close menu windows with fade effect
   */
  closeMenuWindows() {
    this.menuWindows.forEach(window => {
      if (!window.isDestroyed()) {
        window.webContents.send('fade-out');
        setTimeout(() => {
          window.close();
        }, 300); // Match the CSS transition duration
      }
    });
    this.menuWindows = [];
    this.isMenuVisible = false;
  }

  /**
   * Create menu windows for characters and options
   * @param {Function} updateMenuPositions - Function to update menu positions
   */
  createMenuWindows(updateMenuPositions) {
    const menuSize = 100; // Fixed size of 100px for all menu windows
    const characterFiles = menuUtils.getCharacterFiles();
    const createdWindows = [];
    
    // Create character windows
    characterFiles.forEach((characterName) => {
      const dataUrl = menuUtils.generateCharacterHTML(characterName);
      const menuWindow = new BrowserWindow({
        width: menuSize,
        height: menuSize,
        frame: false,
        transparent: true,
        resizable: false,
        alwaysOnTop: true,
        backgroundColor: '#00000000',
        hasShadow: false,
        focusable: false,
        show: false,
        roundedCorners: false,
        vibrancy: null,
        visualEffectState: null,
        webPreferences: {
          nodeIntegration: true,
          contextIsolation: false
        }
      });

      menuWindow.loadURL(dataUrl);
      createdWindows.push(menuWindow);
    });

    // Create options window with same transparent settings
    const optionsDataUrl = menuUtils.generateOptionsHTML();
    const optionsWindow = new BrowserWindow({
      width: menuSize,
      height: menuSize,
      frame: false,
      transparent: true,
      resizable: false,
      alwaysOnTop: true,
      backgroundColor: '#00000000',
      hasShadow: false,
      focusable: false,
      show: false,
      roundedCorners: false,
      vibrancy: null,
      visualEffectState: null,
      webPreferences: {
        nodeIntegration: true,
        contextIsolation: false
      }
    });

    optionsWindow.loadURL(optionsDataUrl);
    createdWindows.push(optionsWindow);
    
    // Store all windows
    this.menuWindows = createdWindows;
    
    // Position all windows before showing them
    updateMenuPositions();
    
    // Now show all windows with fade-in effect
    this.menuWindows.forEach(window => {
      if (!window.isDestroyed()) {
        window.once('ready-to-show', () => {
          window.webContents.send('fade-in');
          window.show();
        });
      }
    });
    
    this.isMenuVisible = true;
  }

  /**
   * Update the positions of menu windows in a fan layout
   */
  updateMenuPositions() {
    if (!this.mainWindow || this.menuWindows.length === 0) return;

    const mainBounds = this.mainWindow.getBounds();
    
    // Validate the main window bounds
    if (!mainBounds || typeof mainBounds !== 'object' || 
        !Number.isFinite(mainBounds.x) || !Number.isFinite(mainBounds.y) ||
        !Number.isFinite(mainBounds.width) || !Number.isFinite(mainBounds.height)) {
      console.warn('Invalid main window bounds:', mainBounds);
      return;
    }
    
    const centerX = mainBounds.x + mainBounds.width / 2;
    const centerY = mainBounds.y + mainBounds.height / 2;
    
    // Get screen dimensions
    const primaryDisplay = screen.getPrimaryDisplay();
    const screenWidth = primaryDisplay.workAreaSize.width;
    const screenHeight = primaryDisplay.workAreaSize.height;
    
    // Calculate the angle to the center of the screen
    const screenCenterX = screenWidth / 2;
    const screenCenterY = screenHeight / 2;
    const dx = screenCenterX - centerX;
    const dy = screenCenterY - centerY;
    
    // Ensure we have valid values for the angle calculation
    let angleToCenter = 0;
    if (Number.isFinite(dx) && Number.isFinite(dy)) {
      angleToCenter = Math.atan2(dy, dx);
    } else {
      console.warn('Invalid values for angle calculation:', { dx, dy, centerX, centerY });
    }
    
    // Calculate the start and end angles for the 120-degree fan
    // The fan opens towards the center of the screen
    const fanAngle = 2 * Math.PI / 3; // 120 degrees in radians (2 * PI / 3)
    const startAngle = angleToCenter - fanAngle / 2;
    const endAngle = angleToCenter + fanAngle / 2;
    
    // Calculate radius for the fan shape
    const radius = 225; // Increased distance from main window center for fixed-size windows
    
    // Calculate angle step to distribute windows evenly in the 120-degree fan
    const angleStep = this.menuWindows.length > 1 
      ? (endAngle - startAngle) / (this.menuWindows.length - 1)
      : 0;
    
    // Fixed menu window size (100px)
    const windowSize = 100;
    const halfSize = 50; // Half of the fixed window size
    
    // Filter out closed windows and update positions
    this.menuWindows = this.menuWindows.filter(window => {
      if (!window || window.isDestroyed()) return false;
      
      try {
        // Calculate position on the fan
        const index = this.menuWindows.indexOf(window);
        const angle = startAngle + (angleStep * index);
        const x = centerX + (radius * Math.cos(angle));
        const y = centerY + (radius * Math.sin(angle));
        
        // Calculate final position (centered on the calculated point)
        const posX = Math.round(x - halfSize);
        const posY = Math.round(y - halfSize);
        
        // Validate coordinates are finite numbers before setting bounds
        if (Number.isFinite(posX) && Number.isFinite(posY)) {
          window.setBounds({
            x: posX,
            y: posY,
            width: windowSize,
            height: windowSize
          });
          return true;
        } else {
          console.warn('Invalid coordinates calculated:', { posX, posY, angle, index });
          return true; // Keep the window, just don't update its position
        }
      } catch (error) {
        console.error('Error updating menu window position:', error);
        return false;
      }
    });
  }

  /**
   * Toggle menu windows visibility
   * @param {Function} updateMenuPositions - Function to update menu positions
   */
  toggleMenuWindows(updateMenuPositions) {
    if (this.isMenuVisible) {
      this.closeMenuWindows();
    } else {
      this.createMenuWindows(updateMenuPositions);
    }
  }

  /**
   * Toggle fullscreen mode of the main window
   */
  toggleShape() {
    if (this.mainWindow) {
      if (this.displayMode === 'circle') {
        // Going from circle to square
        logger.ui(`Setting square mode from ${this.displayMode} state`);
        this.displayMode = 'square';
        
        // Make window resizable in square mode
        this.mainWindow.setResizable(true);
      } else if (this.displayMode === 'square') {
        // Going from square to fullscreen
        logger.ui(`Setting fullscreen mode from ${this.displayMode} state`);
        this.displayMode = 'fullscreen';
        this.previousSize = this.mainWindow.getSize();
        
        // Disable resizing in fullscreen
        this.mainWindow.setResizable(false);
        
        // Force exit fullscreen first to ensure a clean transition
        if (this.mainWindow.isFullScreen()) {
          this.mainWindow.setFullScreen(false);
        }
        
        // Short delay before entering fullscreen for more reliable transition
        setTimeout(() => {
          // Force a proper fullscreen mode
          this.mainWindow.setFullScreen(true);
          
          // Notify the renderer that fullscreen mode has been activated
          setTimeout(() => {
            if (this.mainWindow) {
              this.mainWindow.webContents.send('fullscreen-entered');
            }
          }, 200);
        }, 50);
      } else {
        // Going from fullscreen to circle mode
        // This method is now only used for entering fullscreen
        // Exiting is handled by the restart-window IPC command
        logger.ui('Exiting fullscreen mode');
        this.displayMode = 'circle';
        this.mainWindow.setFullScreen(false);
        
        // Disable resizing in circle mode
        this.mainWindow.setResizable(false);
      }
    }
  }

  /**
   * Toggle fullscreen mode of the main window
   */
  toggleFullscreen() {
    if (this.mainWindow) {
      if (this.mainWindow.isFullScreen()) {
        this.mainWindow.setFullScreen(false);
        this.mainWindow.setSize(this.previousSize[0], this.previousSize[1]);
        
        // If we're in circle mode, ensure transparency is set correctly
        if (this.displayMode === 'circle') {
          this.mainWindow.setBackgroundColor('#00000000');
          this.mainWindow.setVibrancy('under-window');
          this.mainWindow.setHasShadow(false);
          this.mainWindow.setOpacity(1);
        }
      } else {
        this.previousSize = this.mainWindow.getSize();
        this.mainWindow.setFullScreen(true);
      }
    }
  }

  /**
   * Show loading state in the main window
   * @param {boolean} loading - Whether loading is in progress
   */
  setLoadingState(loading) {
    if (this.mainWindow) {
      this.mainWindow.webContents.send('loading-state', loading);
    }
  }

  /**
   * Create a help window that shows keyboard shortcuts
   * @returns {BrowserWindow} - The help window
   */
  createHelpWindow() {
    // If help window already exists, just show it and reset timer
    if (this.helpWindow) {
      if (!this.helpWindow.isDestroyed()) {
        this.helpWindow.show();
        this.helpWindow.webContents.send('reset-timer');
        return this.helpWindow;
      }
    }

    // Get the primary display's work area
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
    
    // Calculate position for top right corner
    const windowWidth = 280; // Increased by 25% from 225
    const windowHeight = 568; // Increased to 600px as requested
    const x = screenWidth - windowWidth - 30; // 30px margin from right edge
    const y = 10; // 50px margin from top edge
    
    // Create the help window
    this.helpWindow = new BrowserWindow({
      width: windowWidth,
      height: windowHeight,
      x: x,
      y: y,
      frame: false,
      transparent: true,
      resizable: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      show: false,
      webPreferences: {
        nodeIntegration: true,
        contextIsolation: false
      }
    });

    // Load the help window HTML
    const helpHtmlPath = path.join(__dirname, '../../renderer/html/help-window.html');
    this.helpWindow.loadFile(helpHtmlPath);

    // Show the window when it's ready
    this.helpWindow.once('ready-to-show', () => {
      this.helpWindow.show();
    });

    // Clean up reference when window is closed
    this.helpWindow.on('closed', () => {
      this.helpWindow = null;
    });

    return this.helpWindow;
  }

  /**
   * Toggle the help window visibility
   */
  toggleHelpWindow() {
    if (this.helpWindow && !this.helpWindow.isDestroyed()) {
      this.helpWindow.close();
      this.helpWindow = null;
    } else {
      this.createHelpWindow();
    }
  }

  /**
   * Close the help window if it exists
   */
  closeHelpWindow() {
    if (this.helpWindow && !this.helpWindow.isDestroyed()) {
      this.helpWindow.close();
      this.helpWindow = null;
    }
  }
}

module.exports = WindowManager; 