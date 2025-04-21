const { app, globalShortcut, BrowserWindow, Menu, MenuItem, dialog, shell, clipboard } = require('electron');
const { ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const fetch = require('node-fetch');
const os = require('os');
const WindowManager = require('./window-manager');
const EventEmitter = require('events');
const config = require('../config');
const logger = require('../utils/logger');

/**
 * AppController class handles application logic and API interactions
 */
class AppController {
  /**
   * Initialize the application controller
   * @param {WindowManager} windowManager - The window manager instance
   */
  constructor(windowManager) {
    this.windowManager = windowManager;
    this.isQuitting = false;
    this.tempDir = path.join(app.getPath('temp'), 'electron-menu-temp');
    
    // Initialize menu utilities with this instance
    const menuUtils = require('../utils/menu-utils');
    menuUtils.init(this);
    
    // Listen for main window recreation
    this.windowManager.on('main-window-recreated', () => {
      this.setupMainWindowHandlers();
    });
  }

  /**
   * Initialize the application
   */
  init() {
    this.setupIPCHandlers();
    
    // Initialize temp directory
    if (!fs.existsSync(this.tempDir)) {
      fs.mkdirSync(this.tempDir, { recursive: true });
    }

    // Set up app event handlers
    app.on('window-all-closed', this.handleWindowAllClosed.bind(this));
    app.on('activate', this.handleActivate.bind(this));
    app.on('before-quit', this.handleBeforeQuit.bind(this));
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
   * Get the assets directory path
   * @returns {string} - Path to assets directory
   */
  getAssetsDirectory() {
    return path.join(this.getUserDataDirectory(), 'assets');
  }

  /**
   * Get path to a specific asset type directory
   * @param {string} assetType - Type of asset (e.g., 'images', 'models', 'voices', 'prompts')
   * @returns {string} - Path to the asset type directory
   */
  getAssetTypeDirectory(assetType) {
    const assetDir = path.join(this.getAssetsDirectory(), assetType);
    
    // Create directory if it doesn't exist
    if (!fs.existsSync(assetDir)) {
      fs.mkdirSync(assetDir, { recursive: true });
      logger.ui(`Created asset directory: ${assetDir}`);
    }
    
    return assetDir;
  }

  /**
   * Get path to a specific asset file
   * @param {string} assetType - Type of asset (e.g., 'images', 'models', 'voices', 'prompts')
   * @param {string} fileName - Name of the asset file
   * @returns {string} - Path to the asset file
   */
  getAssetFilePath(assetType, fileName) {
    return path.join(this.getAssetTypeDirectory(assetType), fileName);
  }

  /**
   * Clean up temporary files
   */
  cleanupTempFiles() {
    try {
      const userDataDir = this.getUserDataDirectory();
      const tempDir = path.join(userDataDir, 'temp');
      
      if (fs.existsSync(tempDir)) {
        fs.readdirSync(tempDir).forEach(file => {
          const filePath = path.join(tempDir, file);
          try {
            if (fs.lstatSync(filePath).isDirectory()) {
              fs.rmdirSync(filePath, { recursive: true });
            } else {
              fs.unlinkSync(filePath);
            }
          } catch (err) {
            logger.error(`Error deleting ${filePath}: ${err}`, logger.LogCategory.SYSTEM);
          }
        });
      }
    } catch (error) {
      logger.error(`Error cleaning up temp files: ${error}`, logger.LogCategory.SYSTEM);
    }
  }

  /**
   * Check if model is still loading
   * @returns {Promise<boolean>} - True if model is reloading
   */
  async checkLoadingStatus() {
    try {
      const response = await fetch(`http://127.0.0.1:${config.SERVER_PORT}${config.API_ENDPOINTS.STATUS}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      return data.is_reloading;
    } catch (error) {
      logger.error(`Error checking loading status: ${error.message}`, logger.LogCategory.NETWORK);
      return false;
    }
  }

  /**
   * Wait for model reload to complete
   * @returns {Promise<boolean>} - True when reload is complete
   */
  async waitForModelReload() {
    const maxWaitTime = 30000; // 30 seconds timeout
    const startTime = Date.now();
    
    while (true) {
      // Check if we've exceeded the timeout
      if (Date.now() - startTime > maxWaitTime) {
        logger.error('Timeout waiting for model reload', logger.LogCategory.MODEL);
        return false;
      }
      
      try {
        const isReloading = await this.checkLoadingStatus();
        if (!isReloading) {
          return true;
        }
        
        // Log progress every 5 seconds
        if (Math.floor((Date.now() - startTime) / 5000) === (Date.now() - startTime) / 5000) {
          logger.model(`Still waiting for model reload... ${Math.floor((Date.now() - startTime) / 1000)}s elapsed`);
        }
        
        await new Promise(resolve => setTimeout(resolve, 500)); // Check every 500ms
      } catch (error) {
        logger.error(`Error while waiting for model reload: ${error.message}`, logger.LogCategory.MODEL);
        // If we can't check status, we'll assume reload failed after a few retries
        await new Promise(resolve => setTimeout(resolve, 1000));
        // If this error persists for 5 seconds, we'll give up
        if (Date.now() - startTime > 5000) {
          return false;
        }
      }
    }
  }

  /**
   * Reload a character model
   * @param {string} characterName - Name of character to reload
   */
  async reloadCharacterModel(characterName) {
    try {
      logger.model(`Sending reload request for character: ${characterName}`);
      
      // Show loading overlay
      this.windowManager.setLoadingState(true);
      
      // Get the absolute path to the model file using our helpers
      const modelPath = this.getAssetFilePath('models', `${characterName}.imx`);
      
      logger.model(`Using model path: ${modelPath}`);
      
      // Save the selected model to settings.json
      this.saveSettings({ model: characterName });
      logger.model(`Saved selected model to settings: ${characterName}`);
      
      // Get current settings to include prompt and voice in the request
      const settings = this.getSettings();
      
      const response = await fetch(`http://127.0.0.1:${config.SERVER_PORT}${config.API_ENDPOINTS.RELOAD_MODEL}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model_path: modelPath,
          prompt: settings.prompt,
          voice: settings.voice,
          force_reload: true  // Always force reload to ensure settings changes take effect
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      logger.model(`Model reload response: ${JSON.stringify(data, null, 2)}`);
      
      // Wait for model to finish reloading
      logger.model('Waiting for model to finish reloading...');
      const reloadSuccess = await this.waitForModelReload();
      
      // Hide loading overlay
      this.windowManager.setLoadingState(false);
      
      if (reloadSuccess) {
        logger.model('Model reload complete!');
        
        // Notify main window about successful reload
        if (this.windowManager.mainWindow) {
          this.windowManager.mainWindow.webContents.send('model-reload-status', {
            success: true,
            characterName: characterName
          });
        }
      } else {
        logger.error('Model reload timed out or failed', logger.LogCategory.MODEL);
        
        // Notify main window about failed reload
        if (this.windowManager.mainWindow) {
          this.windowManager.mainWindow.webContents.send('model-reload-status', {
            success: false,
            characterName: characterName,
            error: 'Model reload timed out or failed'
          });
        }
        
        // Show an error dialog
        dialog.showErrorBox(
          'Model Reload Failed',
          `The ${characterName} model failed to reload. Please try again or check server logs for details.`
        );
      }
      
    } catch (error) {
      // Hide loading overlay on error
      this.windowManager.setLoadingState(false);
      logger.error(`Error reloading character model: ${error}`, logger.LogCategory.MODEL);
      
      // Notify main window about error
      if (this.windowManager.mainWindow) {
        this.windowManager.mainWindow.webContents.send('model-reload-status', {
          success: false,
          characterName: characterName,
          error: error.message
        });
      }
      
      // Show an error dialog
      dialog.showErrorBox(
        'Model Reload Error',
        `Failed to reload ${characterName} model: ${error.message}`
      );
    }
  }

  /**
   * Create application menu
   */
  createMenu() {
    const template = [
      {
        label: 'File',
        submenu: [
          {
            label: 'Options',
            click: () => {
              this.windowManager.createSettingsWindow(() => {
                if (this.windowManager.mainWindow) {
                  this.windowManager.mainWindow.show();
                  this.windowManager.mainWindow.webContents.send('fade-in');
                }
              });
            }
          },
          { type: 'separator' },
          {
            label: 'Quit',
            accelerator: process.platform === 'darwin' ? 'Command+Q' : 'Alt+F4',
            click: () => {
              app.quit();
            }
          }
        ]
      },
      {
        label: 'Edit',
        submenu: [
          { role: 'undo' },
          { role: 'redo' },
          { type: 'separator' },
          { role: 'cut' },
          { role: 'copy' },
          { role: 'paste' },
          { role: 'delete' },
          { type: 'separator' },
          { role: 'selectAll' }
        ]
      },
      {
        label: 'View',
        submenu: [
          { role: 'reload' },
          { role: 'forceReload' },
          { role: 'toggleDevTools' },
          { type: 'separator' },
          { role: 'resetZoom' },
          { role: 'zoomIn' },
          { role: 'zoomOut' },
          { type: 'separator' },
          { role: 'togglefullscreen' }
        ]
      },
      {
        role: 'window',
        submenu: [
          { role: 'minimize' },
          { role: 'zoom' },
          { type: 'separator' },
          { role: 'front' },
          { type: 'separator' },
          { role: 'window' }
        ]
      },
      {
        role: 'help',
        submenu: [
          {
            label: 'Learn More',
            click: async () => {
              await shell.openExternal('https://electronjs.org');
            }
          }
        ]
      }
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
  }

  /**
   * Set up context menu for the main window
   * @param {BrowserWindow} mainWindow - The main application window
   */
  setupContextMenu(mainWindow) {
    mainWindow.webContents.on('context-menu', (event, params) => {
      // Directly toggle menu windows instead of showing a context menu
      this.windowManager.toggleMenuWindows(
        this.windowManager.updateMenuPositions.bind(this.windowManager)
      );
      
      // Prevent the default context menu from showing
      event.preventDefault();
    });
  }

  /**
   * Handle minimize keyboard shortcut
   * @param {BrowserWindow} mainWindow - The main application window
   */
  handleMinimizeShortcut(mainWindow) {
    mainWindow.webContents.on('before-input-event', (event, input) => {
      if (input.key === 's' && !input.control && !input.meta && !input.alt) {
        event.preventDefault();
        // Close all menu windows if they're visible
        if (this.windowManager.isMenuVisible) {
          this.windowManager.closeMenuWindows();
        }
        mainWindow.minimize();
      }
      
      // Handle 'h' key to toggle help window
      if (input.key === 'h' && !input.control && !input.meta && !input.alt) {
        event.preventDefault();
        logger.ui('Toggle help window via keyboard shortcut');
        this.windowManager.toggleHelpWindow();
      }
    });
  }

  /**
   * Handle window-all-closed event
   */
  handleWindowAllClosed() {
    if (process.platform !== 'darwin') {
      app.quit();
    }
  }

  /**
   * Handle activate event
   */
  handleActivate() {
    if (this.windowManager.mainWindow === null) {
      this.createMainWindow();
    }
  }

  /**
   * Handle before-quit event
   */
  handleBeforeQuit() {
    this.isQuitting = true;
    this.cleanupTempFiles();
  }

  /**
   * Create the main window
   */
  createMainWindow() {
    this.windowManager.createMainWindow(
      this.setupContextMenu.bind(this),
      this.handleMinimizeShortcut.bind(this),
      this.windowManager.updateMenuPositions.bind(this.windowManager)
    );

    // Prevent window from being closed unless quitting
    this.windowManager.mainWindow.on('close', (event) => {
      if (!this.isQuitting) {
        event.preventDefault();
      }
    });
  }

  /**
   * Set up event handlers for a newly created main window
   * This method can be called when the main window is recreated
   */
  setupMainWindowHandlers() {
    if (this.windowManager.mainWindow) {
      // Set up context menu
      this.setupContextMenu(this.windowManager.mainWindow);
      
      // Add keyboard shortcut handler
      this.handleMinimizeShortcut(this.windowManager.mainWindow);
      
      // Set up menu position updates
      this.windowManager.mainWindow.on('moved', () => {
        if (this.windowManager.isMenuVisible) {
          this.windowManager.updateMenuPositions();
        }
      });
      
      // Prevent window from being closed unless quitting
      this.windowManager.mainWindow.on('close', (event) => {
        if (!this.isQuitting) {
          event.preventDefault();
        }
      });
    }
  }

  /**
   * Get available models from the filesystem
   * @returns {Array} Array of model objects with id and name
   */
  getAvailableModels() {
    try {
      const modelsDir = this.getAssetTypeDirectory('models');
      logger.model(`Scanning for models in: ${modelsDir}`);
      
      if (!fs.existsSync(modelsDir)) {
        logger.error(`Models directory not found: ${modelsDir}`, logger.LogCategory.MODEL);
        return [];
      }
      
      // Get all .imx files in the directory
      const files = fs.readdirSync(modelsDir).filter(f => f.endsWith('.imx'));
      logger.model(`Found ${files.length} model files in ${modelsDir}`);
      
      // Create model objects from files with modification time
      const models = files.map(file => {
        const filePath = path.join(modelsDir, file);
        const stats = fs.statSync(filePath);
        const id = file.replace('.imx', '');
        const displayName = id.split('_')
          .map(word => word.charAt(0).toUpperCase() + word.slice(1))
          .join(' ');
        
        // Also get the image file stats if it exists
        const imagesDir = this.getAssetTypeDirectory('images');
        const imagePath = path.join(imagesDir, `${id}.jpg`);
        let imageStats = null;
        if (fs.existsSync(imagePath)) {
          imageStats = fs.statSync(imagePath);
        }
        
        // Use image modification time if available (since image is created/copied with model)
        // otherwise fall back to model file time
        const modTime = imageStats ? imageStats.mtime : stats.mtime;
        
        return {
          id: id,
          name: displayName,
          file: filePath,
          modifiedAt: modTime,
          createdAt: stats.birthtime || modTime
        };
      });
      
      // Sort models by modification time (newest first)
      models.sort((a, b) => {
        return new Date(b.modifiedAt) - new Date(a.modifiedAt);
      });
      
      return models;
    } catch (error) {
      logger.error(`Error getting available models: ${error}`, logger.LogCategory.MODEL);
      return [];
    }
  }

  /**
   * Setup all IPC handlers
   */
  setupIPCHandlers() {
    // Handle quit command from renderer
    ipcMain.on('quit', () => {
      this.isQuitting = true;
      if (this.windowManager.mainWindow) {
        this.windowManager.mainWindow.close();
      }
      app.quit();
    });

    // Handle minimize window command
    ipcMain.on('minimize-window', () => {
      if (this.windowManager.mainWindow) {
        this.windowManager.mainWindow.minimize();
      }
    });

    // Handle shape toggle command from renderer
    ipcMain.on('toggle-shape', () => {
      this.windowManager.toggleShape();
      
      // Notification is now handled directly in the toggleShape method
    });

    // Handle fullscreen toggle command from renderer
    ipcMain.on('toggle-fullscreen', () => {
      this.windowManager.toggleFullscreen();
    });

    ipcMain.on('open-settings', () => {
      // Signal main window that settings are opening
      if (this.windowManager.mainWindow) {
        this.windowManager.mainWindow.webContents.send('settings-opening');
      }
      
      this.windowManager.createSettingsWindow(() => {
        if (this.windowManager.mainWindow) {
          this.windowManager.mainWindow.show();
          this.windowManager.mainWindow.webContents.send('fade-in');
          
          // Signal main window that settings are closed
          this.windowManager.mainWindow.webContents.send('settings-closed');
        }
      });
    });

    // Handle menu toggle command from renderer
    ipcMain.on('toggle-menu', () => {
      this.windowManager.toggleMenuWindows(
        this.windowManager.updateMenuPositions.bind(this.windowManager)
      );
    });

    // Handle menu item clicked
    ipcMain.on('menu-item-clicked', (event, type, data) => {
      // Close all menu windows immediately
      this.windowManager.closeMenuWindows();

      // Handle different menu item types
      if (type === 'options') {
        // Signal main window that settings are opening
        if (this.windowManager.mainWindow) {
          this.windowManager.mainWindow.webContents.send('settings-opening');
        }
        
        this.windowManager.createSettingsWindow(() => {
          if (this.windowManager.mainWindow) {
            this.windowManager.mainWindow.show();
            this.windowManager.mainWindow.webContents.send('fade-in');
            
            // Signal main window that settings are closed
            this.windowManager.mainWindow.webContents.send('settings-closed');
          }
        });
      } else if (type === 'character') {
        logger.model(`Character selected: ${data}`);
        this.reloadCharacterModel(data);
      }
    });

    // Close menu windows
    ipcMain.on('close-menu', () => {
      this.windowManager.closeMenuWindows();
    });

    // Handle help window toggling and closing
    ipcMain.on('toggle-help-window', () => {
      this.windowManager.toggleHelpWindow();
    });
    
    ipcMain.on('close-help-window', () => {
      this.windowManager.closeHelpWindow();
    });

    // Add IPC handler for opening external URLs
    ipcMain.on('open-external-url', (event, url) => {
      shell.openExternal(url);
    });

    // Add IPC handler for opening file dialog
    ipcMain.on('open-file-dialog', async (event, options) => {
      const result = await dialog.showOpenDialog({
        properties: ['openFile'],
        filters: options.filters
      });
      
      if (!result.canceled && result.filePaths.length > 0) {
        event.sender.send('file-selected', result.filePaths[0]);
      }
    });

    // Add IPC handler for closing settings window
    ipcMain.on('close-settings-window', () => {
      logger.system('Received close-settings-window event');
      
      // Get current settings for comparison
      const currentSettings = this.getSettings();
      const modelToReload = currentSettings?.model;
      
      // Retrieve the settings that were active when the window was opened
      const originalSettings = this.windowManager.settingsWindowOpenedWith;
      
      logger.system('Current settings before closing settings window');
      logger.system('Original settings when window was opened');
      
      if (this.windowManager.settingsWindow) {
        logger.ui('Closing settings window...');
        
        // Force closing the window by destroying it (bypassing any close event prevention)
        this.windowManager.settingsWindow.destroy();
        
        logger.ui('Settings window closed');
        
        // Check if settings have changed by doing a deep comparison
        const settingsChanged = this.haveSettingsChanged(originalSettings, currentSettings);
        
        // After closing the settings window, check if we need to reload the model
        if (settingsChanged && modelToReload) {
          logger.model(`Settings have changed. Will reload model: ${modelToReload}`);
          
          // Use a longer delay to ensure everything is saved properly
          setTimeout(() => {
            logger.model(`Now reloading model: ${modelToReload}`);
            this.reloadCharacterModel(modelToReload);
          }, 1000);
        } else {
          if (!settingsChanged) {
            logger.system('Settings have not changed. No need to reload model.');
          } else if (!modelToReload) {
            logger.system('No model found in settings to reload.');
          }
        }
      } else {
        logger.warn('Settings window not found, cannot close', logger.LogCategory.UI);
      }
    });

    // Handle model selection
    ipcMain.on('select-model', (event, modelName) => {
      logger.model(`Selected model: ${modelName}`);
      // Save the model selection only if valid
      if (modelName && typeof modelName === 'string' && modelName.trim() !== '') {
        this.saveSettings({ model: modelName });
      }
    });

    // Handle voice selection
    ipcMain.on('select-voice', (event, voiceName) => {
      logger.model(`Selected voice: ${voiceName}`);
      // Save the voice selection only if valid
      if (voiceName && typeof voiceName === 'string' && voiceName.trim() !== '') {
        this.saveSettings({ voice: voiceName });
      }
    });

    // Handle API key saving
    ipcMain.on('save-api-key', (event, data) => {
      logger.system(`Saving API key for ${data.service}`);
      
      // Only proceed if we have a valid service and key
      if (!data.service || !data.key || data.key.trim() === '') {
        logger.warn(`Invalid API key data for ${data.service}, not saving`, logger.LogCategory.SYSTEM);
        return;
      }
      
      // Check if this is a masked key (containing many asterisks)
      if (data.key.includes('*') && data.key.match(/\*{4,}/)) {
        logger.system(`Detected masked API key for ${data.service}, not saving`);
        return;
      }
      
      // Get current settings
      const settings = this.getSettings();
      if (!settings.apiKeys) {
        settings.apiKeys = {};
      }
      // Update the API key
      settings.apiKeys[data.service] = data.key;
      // Save updated settings
      this.saveSettings(settings);
    });

    // Handle import model
    ipcMain.on('import-model', async (event, filePath) => {
      logger.model(`Importing model from: ${filePath}`, 'INFO');
      
      try {
        // Get the model name from the file path
        const modelFileName = path.basename(filePath);
        const modelName = path.basename(filePath, path.extname(filePath));
        
        // Prepare paths for model and image
        const modelsDir = this.getAssetTypeDirectory('models');
        const imagesDir = this.getAssetTypeDirectory('images');
        
        // Create directories if they don't exist
        if (!fs.existsSync(modelsDir)) {
          fs.mkdirSync(modelsDir, { recursive: true });
        }
        if (!fs.existsSync(imagesDir)) {
          fs.mkdirSync(imagesDir, { recursive: true });
        }
        
        const modelDestPath = path.join(modelsDir, modelFileName);
        const imageDestPath = path.join(imagesDir, `${modelName}.jpg`);
        
        // Call API to generate cover photo
        logger.model(`Generating cover photo for model: ${filePath}`, 'INFO');
        
        // Add timeout to prevent hanging
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout
        
        try {
          // Make a POST request to the cover photo generation API
          const response = await fetch(`http://127.0.0.1:${config.SERVER_PORT}/api/get_cover_photo_from_model`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              model_path: filePath
            }),
            signal: controller.signal
          });
          
          clearTimeout(timeoutId);
          
          // Check if the request was successful
          if (!response.ok) {
            throw new Error(`API request failed with status: ${response.status}`);
          }
          
          // Parse the response
          const data = await response.json();
          
          // Check if the cover photo was generated successfully
          if (!data.success || !data.cover_photo_path) {
            throw new Error('Failed to generate cover photo');
          }
          
          // Send the temporary cover photo path back to the renderer to show the preview
          event.sender.send('show-model-preview', {
            modelPath: filePath,
            coverPhotoPath: data.cover_photo_path,
            modelName: modelName
          });
        } catch (fetchError) {
          clearTimeout(timeoutId);
          
          // Specific handling for network errors
          if (fetchError.name === 'AbortError') {
            throw new Error('Request timed out while generating cover photo');
          }
          
          throw fetchError;
        }
        
      } catch (error) {
        logger.error(`Error importing model: ${error.message}`, logger.LogCategory.MODEL);
        // Show an error dialog
        dialog.showErrorBox(
          'Model Import Error',
          `Failed to import model: ${error.message}`
        );
        
        // Notify the renderer of the error
        event.sender.send('model-import-error', {
          error: error.message
        });
      }
    });
    
    // Handle model import confirmation
    ipcMain.on('confirm-model-import', async (event, data) => {
      try {
        const { modelPath, coverPhotoPath, shouldDelete } = data;
        
        // Get the model name from the file path
        const modelFileName = path.basename(modelPath);
        const modelName = path.basename(modelPath, path.extname(modelPath));
        
        // Prepare paths for model and image
        const modelsDir = this.getAssetTypeDirectory('models');
        const imagesDir = this.getAssetTypeDirectory('images');
        
        const modelDestPath = path.join(modelsDir, modelFileName);
        const imageDestPath = path.join(imagesDir, `${modelName}.jpg`);
        
        // Add a small delay to allow any in-progress operations to complete
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Copy or move the model file based on user preference
        if (shouldDelete) {
          try {
            // Move the file (cut & paste)
            fs.renameSync(modelPath, modelDestPath);
            logger.model(`Moved model file from ${modelPath} to ${modelDestPath}`, 'INFO');
          } catch (moveError) {
            // If move fails (e.g., across different filesystems), try copy and delete
            logger.warn(`Move operation failed, falling back to copy + delete: ${moveError.message}`, logger.LogCategory.MODEL);
            fs.copyFileSync(modelPath, modelDestPath);
            // Only try to delete if copy succeeded
            try {
              fs.unlinkSync(modelPath);
            } catch (unlinkError) {
              logger.warn(`Warning: Could not delete original file: ${unlinkError.message}`, logger.LogCategory.MODEL);
            }
          }
        } else {
          // Copy the file
          fs.copyFileSync(modelPath, modelDestPath);
          logger.model(`Copied model file from ${modelPath} to ${modelDestPath}`, 'INFO');
        }
        
        // Move the generated cover photo to the images directory
        if (fs.existsSync(coverPhotoPath)) {
          fs.copyFileSync(coverPhotoPath, imageDestPath);
          logger.model(`Copied cover photo from ${coverPhotoPath} to ${imageDestPath}`, 'INFO');
          
          // Clean up temporary cover photo
          try {
            fs.unlinkSync(coverPhotoPath);
            logger.model(`Deleted temporary cover photo: ${coverPhotoPath}`, 'INFO');
          } catch (err) {
            logger.warn(`Could not delete temporary cover photo: ${err.message}`, logger.LogCategory.MODEL);
          }
        } else {
          logger.warn(`Cover photo not found at ${coverPhotoPath}, skipping copy`, logger.LogCategory.MODEL);
        }
        
        // Add another small delay to ensure file operations complete
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Notify all windows about the model update
        this.syncModelsAcrossWindows();
        
        // Notify the renderer to refresh the models grid
        event.sender.send('model-import-complete', {
          modelName: modelName,
          modelPath: modelDestPath,
          imagePath: imageDestPath
        });
        
      } catch (error) {
        logger.error(`Error finalizing model import: ${error.message}`, logger.LogCategory.MODEL);
        
        // Show an error dialog
        dialog.showErrorBox(
          'Model Import Error',
          `Failed to finalize model import: ${error.message}`
        );
        
        // Notify the renderer of the error
        event.sender.send('model-import-error', {
          error: error.message
        });
      }
    });

    // Handle cleanup of temporary files
    ipcMain.on('cleanup-temporary-files', (event, data) => {
      logger.model('Cleaning up temporary files', 'INFO');
      
      try {
        // Delete temporary cover photo
        if (data.coverPhotoPath && fs.existsSync(data.coverPhotoPath)) {
          fs.unlinkSync(data.coverPhotoPath);
          logger.model(`Deleted temporary cover photo: ${data.coverPhotoPath}`, 'INFO');
        }
      } catch (error) {
        logger.error(`Error cleaning up temporary files: ${error.message}`, logger.LogCategory.MODEL);
      }
    });

    // Handle model deletion
    ipcMain.on('delete-model', (event, data) => {
      logger.model(`Deleting model: ${data.modelId}`, 'INFO');
      
      try {
        // Don't allow deletion of the default model
        if (data.modelId === 'albert_einstein') {
          throw new Error('Cannot delete the default model');
        }
        
        // Get the path to the model and image files
        const modelsDir = this.getAssetTypeDirectory('models');
        const imagesDir = this.getAssetTypeDirectory('images');
        
        const modelPath = path.join(modelsDir, `${data.modelId}.imx`);
        const imagePath = path.join(imagesDir, `${data.modelId}.jpg`);
        
        logger.model(`Model file path: ${modelPath}`, 'INFO');
        logger.model(`Image file path: ${imagePath}`, 'INFO');
        
        // Check if files exist before attempting to delete
        let modelDeleted = false;
        let imageDeleted = false;
        
        // Delete model file if it exists
        if (fs.existsSync(modelPath)) {
          fs.unlinkSync(modelPath);
          modelDeleted = true;
          logger.model(`Deleted model file: ${modelPath}`, 'INFO');
        } else {
          logger.warn(`Model file not found: ${modelPath}`, logger.LogCategory.MODEL);
        }
        
        // Delete image file if it exists
        if (fs.existsSync(imagePath)) {
          fs.unlinkSync(imagePath);
          imageDeleted = true;
          logger.model(`Deleted image file: ${imagePath}`, 'INFO');
        } else {
          logger.warn(`Image file not found: ${imagePath}`, logger.LogCategory.MODEL);
        }
        
        // If this was the selected model, update settings to use the default model
        if (data.isSelected) {
          logger.model('Deleted model was the selected one, switching to default model', 'INFO');
          this.saveSettings({ model: 'albert_einstein' });
        }
        
        // Sync models across all windows
        this.syncModelsAcrossWindows();
        
        // Send success response
        event.sender.send('model-deleted', {
          success: true,
          modelId: data.modelId,
          modelName: data.modelId.split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' '),
          modelDeleted,
          imageDeleted,
          wasSelected: data.isSelected
        });
        
      } catch (error) {
        logger.error(`Error deleting model: ${error.message}`, logger.LogCategory.MODEL);
        
        // Send error response
        event.sender.send('model-deleted', {
          success: false,
          modelId: data.modelId,
          error: error.message
        });
      }
    });

    // Handle getting all settings
    ipcMain.on('get-settings', (event) => {
      const settings = this.getSettings();
      event.sender.send('settings-data', settings);
    });

    // Handle saving all settings
    ipcMain.on('save-all-settings', (event, settings) => {
      logger.system('Received settings to save');
      
      // Filter out null, undefined, or empty string values
      const filteredSettings = {};
      
      // Process top-level properties
      Object.keys(settings).forEach(key => {
        const value = settings[key];
        
        // Special handling for apiKeys object
        if (key === 'apiKeys' && value && typeof value === 'object') {
          const filteredApiKeys = {};
          let hasKeys = false;
          
          Object.keys(value).forEach(apiKey => {
            const keyValue = value[apiKey];
            // Only save if it's a valid key value and not a masked value
            if (keyValue && typeof keyValue === 'string' && keyValue.trim() !== '') {
              // Skip masked keys (containing many asterisks)
              if (keyValue.includes('*') && keyValue.match(/\*{4,}/)) {
                logger.system(`Skipping masked API key for ${apiKey}`);
                return;
              }
              
              filteredApiKeys[apiKey] = keyValue;
              hasKeys = true;
            }
          });
          
          if (hasKeys) {
            filteredSettings.apiKeys = filteredApiKeys;
          }
        } 
        // Handle other properties
        else if (value !== null && value !== undefined && 
                (typeof value !== 'string' || value.trim() !== '')) {
          filteredSettings[key] = value;
        }
      });
      
      // Only save if we have settings to save
      if (Object.keys(filteredSettings).length > 0) {
        logger.system('Saving filtered settings');
        this.saveSettings(filteredSettings);
      } else {
        logger.system('No valid settings to save after filtering');
      }
    });

    // Show context menu
    ipcMain.on('show-context-menu', (event) => {
      if (this.windowManager.mainWindow) {
        // Directly toggle menu windows instead of showing a context menu
        this.windowManager.toggleMenuWindows(
          this.windowManager.updateMenuPositions.bind(this.windowManager)
        );
      }
    });

    // Handle asset paths request from renderer
    ipcMain.on('get-asset-paths', (event) => {
      try {
        logger.ui('Received request for asset paths from renderer');
        
        // Create asset directories if they don't exist
        const assetsDir = this.getAssetsDirectory();
        if (!fs.existsSync(assetsDir)) {
          logger.ui(`Creating main assets directory: ${assetsDir}`);
          fs.mkdirSync(assetsDir, { recursive: true });
        }
        
        // Ensure all asset type directories exist
        const assetTypes = ['images', 'prompts', 'voices', 'models'];
        const paths = {};
        
        assetTypes.forEach(type => {
          const typePath = this.getAssetTypeDirectory(type);
          paths[`${type}Path`] = typePath;
          
          // Explicitly log each path for debugging
          logger.ui(`Asset ${type} directory: ${typePath} (exists: ${fs.existsSync(typePath)})`);
        });
        
        // Double check prompts.json path specifically since that's causing issues
        const promptsPath = path.join(paths.promptsPath, 'prompts.json');
        logger.ui(`Checking for prompts.json at: ${promptsPath} (exists: ${fs.existsSync(promptsPath)})`);
        
        // If prompts.json doesn't exist in the prompts path, attempt to copy from project root if it exists
        if (!fs.existsSync(promptsPath)) {
          logger.ui('prompts.json not found in user data directory, checking project root...');
          
          const projectRoot = path.resolve(__dirname, '../../../../');
          const sourcePromptsPath = path.join(projectRoot, 'assets', 'prompts', 'prompts.json');
          
          if (fs.existsSync(sourcePromptsPath)) {
            logger.ui(`Found prompts.json in project root, copying to: ${promptsPath}`);
            try {
              // Copy file
              fs.copyFileSync(sourcePromptsPath, promptsPath);
              logger.ui('Successfully copied prompts.json to user data directory');
            } catch (copyError) {
              logger.error(`Error copying prompts.json: ${copyError}`, logger.LogCategory.SYSTEM);
            }
          } else {
            logger.ui('prompts.json not found in project root either');
          }
        }
        
        // Check the user's home directory as a last resort
        if (!fs.existsSync(promptsPath)) {
          const homedir = require('os').homedir();
          const macPath = path.join(homedir, 'Library', 'Application Support', 'bitHumanVisualAgent', 'assets', 'prompts', 'prompts.json');
          
          if (fs.existsSync(macPath) && macPath !== promptsPath) {
            logger.ui(`Found prompts.json in standard macOS path: ${macPath}`);
            try {
              // Copy file
              fs.copyFileSync(macPath, promptsPath);
              logger.ui('Successfully copied prompts.json from macOS standard path');
            } catch (copyError) {
              logger.error(`Error copying prompts.json from macOS path: ${copyError}`, logger.LogCategory.SYSTEM);
            }
          }
        }
        
        // Send the paths to the renderer
        logger.ui('Sending asset paths to renderer');
        event.sender.send('asset-paths', paths);
      } catch (error) {
        logger.error(`Error handling get-asset-paths request: ${error}`, logger.LogCategory.SYSTEM);
        
        // Try to send at least some paths
        const fallbackPaths = {
          imagesPath: path.join(app.getPath('userData'), 'assets', 'images'),
          promptsPath: path.join(app.getPath('userData'), 'assets', 'prompts'),
          voicesPath: path.join(app.getPath('userData'), 'assets', 'voices'),
          modelsPath: path.join(app.getPath('userData'), 'assets', 'models')
        };
        
        logger.ui('Sending fallback paths to renderer');
        event.sender.send('asset-paths', fallbackPaths);
      }
    });

    // Add handler for getting models from filesystem
    ipcMain.on('get-models-from-filesystem', (event) => {
      logger.model('Received request for models from filesystem');
      const models = this.getAvailableModels();
      logger.model(`Sending ${models.length} models to renderer`);
      event.sender.send('models-from-filesystem', models);
    });
    
    // Add handler to sync all windows with current models
    ipcMain.on('sync-models', (event) => {
      const models = this.getAvailableModels();
      
      // Send models to all open windows
      if (this.windowManager.mainWindow) {
        this.windowManager.mainWindow.webContents.send('models-updated', models);
      }
      
      if (this.windowManager.settingsWindow) {
        this.windowManager.settingsWindow.webContents.send('models-updated', models);
      }
      
      // Also send back to the requesting window
      event.sender.send('models-updated', models);
    });

    // Add IPC handler for getting API keys
    ipcMain.on('get-api-keys', (event) => {
      logger.system('Received get-api-keys request');
      try {
        // Get current settings
        const settings = this.getSettings();
        
        // Create an object with API keys
        const apiKeys = {
          bithuman: settings?.apiKeys?.bithuman || '',
          openai: settings?.apiKeys?.openai || ''
        };
        
        // Send API keys to renderer
        event.sender.send('api-keys', apiKeys);
      } catch (error) {
        logger.error(`Error getting API keys: ${error}`, logger.LogCategory.SYSTEM);
        // Send empty object if error occurs
        event.sender.send('api-keys', { bithuman: '', openai: '' });
      }
    });

    // Add handler for restarting the window cleanly
    ipcMain.on('restart-window', () => {
      logger.ui("Restarting main window...");
      
      // Close existing window safely
      if (this.windowManager.mainWindow) {
        // First make sure we're out of fullscreen
        if (this.windowManager.mainWindow.isFullScreen()) {
          this.windowManager.mainWindow.setFullScreen(false);
        }
        
        // Close the window
        this.windowManager.mainWindow.destroy();
        this.windowManager.mainWindow = null;
      }
      
      // Recreate the main window
      this.createMainWindow();
      
      // Show a notification when it's done
      if (this.windowManager.mainWindow) {
        this.windowManager.mainWindow.webContents.once('did-finish-load', () => {
          this.windowManager.mainWindow.webContents.send('window-restarted');
        });
      }
    });
  }

  /**
   * Format settings for display in a visually appealing way
   * Only used for initial logging of settings
   * @param {Object} settings - The settings object to format
   * @param {number} indent - The current indentation level
   * @param {string} parentKey - The parent key (for nested settings)
   */
  formatSettingsForDisplay(settings, indent = 0, parentKey = '') {
    const sensitivePatterns = ['apiKey', 'key', 'secret', 'password', 'token'];
    let output = [];
    
    // Process each key in the settings object
    for (const [key, value] of Object.entries(settings)) {
      const fullKey = parentKey ? `${parentKey}.${key}` : key;
      const isSensitive = sensitivePatterns.some(pattern => key.toLowerCase().includes(pattern));
      
      // Format based on value type
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        // For nested objects, print the key and recursively format
        output.push(`${'  '.repeat(indent)}● ${key}:`);
        output = output.concat(this.formatSettingsForDisplay(value, indent + 1, fullKey));
      } else {
        // For sensitive values, mask them
        let displayValue;
        if (isSensitive) {
          displayValue = value ? '********' : '<empty>';
        } else {
          // Format different value types
          if (value === null) {
            displayValue = 'null';
          } else if (Array.isArray(value)) {
            if (value.length > 3) {
              // For long arrays, show first 3 items and count
              displayValue = `[${value.slice(0, 3).map(v => JSON.stringify(v)).join(', ')}, ... (${value.length} items)]`;
            } else {
              displayValue = `[${value.map(v => JSON.stringify(v)).join(', ')}]`;
            }
          } else {
            displayValue = JSON.stringify(value);
          }
        }
        
        // Add the formatted key-value pair
        output.push(`${'  '.repeat(indent)}  ${key}: ${displayValue}`);
      }
    }
    
    return output;
  }

  // A flag to track if we've already logged the full settings
  fullSettingsLogged = false;

  /**
   * Helper method to get settings
   * @returns {Object} - The current settings
   */
  getSettings() {
    try {
      const userDataPath = this.getUserDataDirectory();
      const settingsPath = path.join(userDataPath, 'settings.json');
      
      if (fs.existsSync(settingsPath)) {
        const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
        
        // Log full settings only once on startup
        if (!this.fullSettingsLogged) {
          logger.system('Initializing with the following settings:');
          const formattedSettings = this.formatSettingsForDisplay(settings);
          formattedSettings.forEach(line => logger.system(line));
          this.fullSettingsLogged = true;
        }
        
        return settings;
      }
    } catch (error) {
      logger.error(`Error reading settings: ${error}`, logger.LogCategory.SYSTEM);
    }
    
    return {}; // Return empty object if settings don't exist or there's an error
  }

  /**
   * Helper method to save settings
   * @param {Object} newSettings - The new settings to save
   */
  saveSettings(newSettings) {
    try {
      const userDataPath = this.getUserDataDirectory();
      const settingsPath = path.join(userDataPath, 'settings.json');
      
      // Get existing settings or create empty object
      let settings = {};
      if (fs.existsSync(settingsPath)) {
        settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
      }
      
      // Track changes for logging
      const changes = this.detectSettingsChanges(settings, newSettings);
      
      // Merge new settings with existing settings
      settings = { ...settings, ...newSettings };
      
      // Write updated settings to file
      fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2));
      
      // Log changes in a more helpful way
      if (Object.keys(changes).length > 0) {
        logger.system(`Updated ${Object.keys(changes).length} settings:`);
        
        // Sort keys for consistent display
        const sensitivePatterns = ['apiKey', 'key', 'secret', 'password', 'token'];
        
        for (const [key, change] of Object.entries(changes).sort()) {
          const isSensitive = sensitivePatterns.some(pattern => key.toLowerCase().includes(pattern));
          
          if (change.old !== undefined) {
            // Changed setting
            if (isSensitive) {
              logger.system(`  • ${key}: [changed]`);
            } else {
              logger.system(`  • ${key}: ${JSON.stringify(change.old)} → ${JSON.stringify(change.new)}`);
            }
          } else {
            // New setting
            if (isSensitive) {
              logger.system(`  • ${key}: [new value added]`);
            } else {
              logger.system(`  • ${key}: ${JSON.stringify(change.new)} [new]`);
            }
          }
        }
      } else {
        logger.system('Settings saved with no changes');
      }
    } catch (error) {
      logger.error(`Error saving settings: ${error}`, logger.LogCategory.SYSTEM);
    }
  }

  /**
   * Detect changes between old and new settings
   * @param {Object} oldSettings - Original settings
   * @param {Object} newSettings - New settings
   * @param {string} path - Current path for nested settings
   * @returns {Object} - Object with changes
   */
  detectSettingsChanges(oldSettings, newSettings, path = '') {
    const changes = {};
    
    // Compare all properties in newSettings with oldSettings
    for (const [key, value] of Object.entries(newSettings)) {
      const currentPath = path ? `${path}.${key}` : key;
      
      // If key doesn't exist in oldSettings, it's a new addition
      if (!(key in oldSettings)) {
        changes[currentPath] = { new: value };
        continue;
      }
      
      // If both values are objects, recurse
      if (
        typeof value === 'object' && value !== null && !Array.isArray(value) &&
          typeof oldSettings[key] === 'object' && oldSettings[key] !== null && !Array.isArray(oldSettings[key])
      ) {
        const nestedChanges = this.detectSettingsChanges(oldSettings[key], value, currentPath);
        Object.assign(changes, nestedChanges);
      }
      // For arrays and primitive values, do direct comparison
      else if (JSON.stringify(oldSettings[key]) !== JSON.stringify(value)) {
        changes[currentPath] = { 
          old: oldSettings[key],
          new: value
        };
      }
    }
    
    return changes;
  }

  /**
   * Sync models across all open windows
   */
  syncModelsAcrossWindows() {
    const models = this.getAvailableModels();
    
    // Send models to all open windows
    if (this.windowManager.mainWindow) {
      this.windowManager.mainWindow.webContents.send('models-updated', models);
    }
    
    if (this.windowManager.settingsWindow) {
      this.windowManager.settingsWindow.webContents.send('models-updated', models);
    }
  }

  /**
   * Refresh the server port by re-importing the config module
   * This ensures we always use the latest port from settings.json
   */
  refreshServerPort() {
    try {
      // Clear require cache for the config module
      delete require.cache[require.resolve('../config')];
      // Re-import the config module
      const config = require('../config');
      logger.system(`Refreshed server port: ${config.SERVER_PORT}`);
      return config.SERVER_PORT;
    } catch (error) {
      logger.error(`Error refreshing server port: ${error}`, logger.LogCategory.SYSTEM);
      // Return default if refresh fails
      return 5001;
    }
  }

  /**
   * Create the settings window
   */
  createSettingsWindow() {
    logger.ui('Opening settings window');
    
    this.windowManager.createSettingsWindow(() => {
      // Show main window with fade
      if (this.windowManager.mainWindow) {
        this.windowManager.mainWindow.show();
        this.windowManager.mainWindow.webContents.send('fade-in');
      }
    });
    
    // Make sure the settings window has the latest models list
    setTimeout(() => {
      this.syncModelsAcrossWindows();
    }, 500);
  }

  /**
   * Helper method to check if settings have changed
   * @param {Object} originalSettings - The original settings
   * @param {Object} currentSettings - The current settings
   * @returns {boolean} - True if settings have changed
   */
  haveSettingsChanged(originalSettings, currentSettings) {
    if (!originalSettings || !currentSettings) {
      return true; // If we don't have both settings objects, assume they changed
    }
    
    // Check model
    if (originalSettings.model !== currentSettings.model) {
      logger.model(`Model changed from ${originalSettings.model} to ${currentSettings.model}`);
      return true;
    }
    
    // Check prompt
    if (originalSettings.prompt !== currentSettings.prompt) {
      logger.model('Prompt changed');
      return true;
    }
    
    // Check voice
    if (originalSettings.voice !== currentSettings.voice) {
      logger.model(`Voice changed from ${originalSettings.voice} to ${currentSettings.voice}`);
      return true;
    }
    
    // Check API keys
    const originalApiKeys = originalSettings.apiKeys || {};
    const currentApiKeys = currentSettings.apiKeys || {};
    
    // Check if API key structures are different
    const originalApiServices = Object.keys(originalApiKeys);
    const currentApiServices = Object.keys(currentApiKeys);
    
    // If different number of API services, settings changed
    if (originalApiServices.length !== currentApiServices.length) {
      logger.model('Different number of API services');
      return true;
    }
    
    // Check each API service key
    for (let i = 0; i < originalApiServices.length; i++) {
      const service = originalApiServices[i];
      if (!currentApiServices.includes(service)) {
        logger.model(`API service ${service} removed`);
        return true;
      }
      
      if (originalApiKeys[service] !== currentApiKeys[service]) {
        logger.model(`API key for ${service} changed`);
        return true;
      }
    }
    
    return false; // No changes detected
  }
}

module.exports = AppController; 