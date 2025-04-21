const { BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');
const logger = require('./logger');

// Store temporary directory reference
let tempDir;
// Store app controller reference
let appController;

/**
 * Initialize utilities with app controller
 * @param {Object} controller - AppController instance
 */
function init(controller) {
  appController = controller;
}

/**
 * Initialize temporary directory
 * @param {string} tempDirPath - Path to temporary directory
 */
function initTempDir(tempDirPath) {
  if (!fs.existsSync(tempDirPath)) {
    fs.mkdirSync(tempDirPath, { recursive: true });
  }
}

/**
 * Get character image as data URL
 * @param {string} characterName - Name of character
 * @returns {string} - Data URL for character image
 */
function getImageDataUrl(characterName) {
  try {
    let imagePath;
    
    // Use app controller if available, otherwise fallback to project root
    if (appController) {
      imagePath = appController.getAssetFilePath('images', `${characterName}.jpg`);
    } else {
      // Fallback to project root path
      const projectRoot = path.resolve(__dirname, '../../../../');
      imagePath = path.join(projectRoot, 'assets/images', `${characterName}.jpg`);
    }
    
    const imageData = fs.readFileSync(imagePath);
    return `data:image/jpeg;base64,${imageData.toString('base64')}`;
  } catch (err) {
    logger.error(`Error loading image for ${characterName}: ${err}`, logger.LogCategory.UI);
    return '';
  }
}

/**
 * Generate HTML content for character menu item
 * @param {string} characterName - Name of character
 * @returns {string} - Data URL containing HTML content
 */
function generateCharacterHTML(characterName) {
  const imageDataUrl = getImageDataUrl(characterName);
  
  const htmlContent = `<!DOCTYPE html>
<html>
<head>
    <title>${characterName}</title>
    <meta charset="UTF-8">
    <style>
        body {
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: rgba(0, 0, 0, 0);
            width: 100vw;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            -webkit-app-region: drag;
            user-select: none;
            opacity: 0;
            transition: opacity 0.3s ease-in-out;
        }

        .menu-item {
            width: 92%;
            height: 92%;
            background: rgba(0, 0, 0, 0);
            border: none;
            outline: none;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s ease;
            -webkit-app-region: no-drag;
            cursor: pointer;
            box-shadow: none;
            position: relative;
            overflow: hidden;
        }

        .menu-item:hover {
            transform: scale(1.05);
        }

        .menu-item img {
            width: 100%;
            height: 100%;
            border-radius: 50%;
            object-fit: cover;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
            position: relative;
            z-index: 1;
        }

        /* Interior spinning border on hover */
        .menu-item::after {
            content: '';
            position: absolute;
            width: 100%;
            height: 100%;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(0deg);
            border-radius: 50%;
            border: 3px solid transparent;
            box-sizing: border-box;
            background: linear-gradient(45deg, #03a9f4, #007bff, #03a9f4) border-box;
            -webkit-mask: 
                linear-gradient(#fff 0 0) padding-box, 
                linear-gradient(#fff 0 0);
            -webkit-mask-composite: destination-out;
            mask-composite: exclude;
            opacity: 0;
            transition: opacity 0.3s ease;
            z-index: 2;
        }

        .menu-item:hover::after {
            opacity: 1;
            animation: spin 2s linear infinite;
        }

        @keyframes spin {
            0% { transform: translate(-50%, -50%) rotate(0deg); }
            100% { transform: translate(-50%, -50%) rotate(360deg); }
        }

        .fade-in {
            opacity: 1;
        }

        .fade-out {
            opacity: 0;
        }
    </style>
</head>
<body>
    <div class="menu-item">
        <img class="character-img" src="${imageDataUrl}" alt="${characterName}">
    </div>
    <script>
        document.querySelector('.menu-item').addEventListener('click', () => {
            require('electron').ipcRenderer.send('menu-item-clicked', 'character', '${characterName}');
        });

        require('electron').ipcRenderer.on('fade-in', () => {
            document.body.classList.add('fade-in');
        });

        require('electron').ipcRenderer.on('fade-out', () => {
            document.body.classList.add('fade-out');
        });
    </script>
</body>
</html>`;

  return `data:text/html;base64,${Buffer.from(htmlContent).toString('base64')}`;
}

/**
 * Get list of character files from assets/images directory
 * @returns {string[]} - Array of character names
 */
function getCharacterFiles() {
  let imagesDir;
  
  // Use app controller if available, otherwise fallback to project root
  if (appController) {
    imagesDir = appController.getAssetTypeDirectory('images');
  } else {
    // Fallback to electron's user data path
    const { app } = require('electron');
    const path = require('path');
    // Use the same app name as in launcher.py
    imagesDir = path.join(app.getPath('userData'), 'assets', 'images');
  }
  
  try {
    logger.ui(`Looking for character files in: ${imagesDir}`);
    
    // Read the directory and filter for .jpg files
    // No longer excluding any characters
    const characters = fs.readdirSync(imagesDir)
      .filter(file => file.endsWith('.jpg'))
      .map(file => file.replace('.jpg', ''));
    
    logger.ui(`Found ${characters.length} character files`);
    
    // Sort characters by modification date (most recent first)
    // and limit to most recent 4 character files
    const sortedCharacters = characters
      .map(character => {
        const filePath = path.join(imagesDir, `${character}.jpg`);
        const stats = fs.statSync(filePath);
        return {
          name: character,
          mtime: stats.mtime.getTime()
        };
      })
      .sort((a, b) => b.mtime - a.mtime)
      .map(item => item.name);
    
    // Return the 4 most recent character files
    if (sortedCharacters.length > 4) {
      logger.ui(`Found ${sortedCharacters.length} character files, returning the 4 most recent`);
      return sortedCharacters.slice(0, 4);
    }
    
    return sortedCharacters;
  } catch (err) {
    logger.error(`Error reading character files: ${err}`, logger.LogCategory.UI);
    return [];
  }
}

/**
 * Generate HTML content for options menu item
 * @returns {string} - Data URL containing HTML content
 */
function generateOptionsHTML() {
  const htmlContent = `<!DOCTYPE html>
<html>
<head>
    <title>Options</title>
    <meta charset="UTF-8">
    <style>
        body {
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: rgba(0, 0, 0, 0);
            width: 100vw;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            -webkit-app-region: drag;
            user-select: none;
            opacity: 0;
            transition: opacity 0.3s ease-in-out;
        }

        .menu-item {
            width: 92%;
            height: 92%;
            background: rgba(0, 0, 0, 0);
            border: none;
            outline: none;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s ease;
            -webkit-app-region: no-drag;
            cursor: pointer;
            box-shadow: none;
            position: relative;
            overflow: hidden;
        }

        .menu-item:hover {
            transform: scale(1.05);
        }

        .settings-circle {
            width: 100%;
            height: 100%;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
            position: relative;
            z-index: 1;
            background: transparent;
        }

        .emoji-icon {
            font-size: 50px;
            transition: all 0.3s ease;
            text-shadow: 0 0 10px rgba(255, 215, 0, 0.6);
        }
        
        .menu-item:hover .emoji-icon {
            transform: scale(1.1);
            text-shadow: 0 0 15px rgba(255, 215, 0, 0.8);
        }

        /* Interior spinning border on hover */
        .menu-item::after {
            content: '';
            position: absolute;
            width: 100%;
            height: 100%;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(0deg);
            border-radius: 50%;
            border: 3px solid transparent;
            box-sizing: border-box;
            background: linear-gradient(45deg, #03a9f4, #007bff, #03a9f4) border-box;
            -webkit-mask: 
                linear-gradient(#fff 0 0) padding-box, 
                linear-gradient(#fff 0 0);
            -webkit-mask-composite: destination-out;
            mask-composite: exclude;
            opacity: 0;
            transition: opacity 0.3s ease;
            z-index: 2;
        }

        .menu-item:hover::after {
            opacity: 1;
            animation: spin 2s linear infinite;
        }

        @keyframes spin {
            0% { transform: translate(-50%, -50%) rotate(0deg); }
            100% { transform: translate(-50%, -50%) rotate(360deg); }
        }

        .fade-in {
            opacity: 1;
        }

        .fade-out {
            opacity: 0;
        }
    </style>
</head>
<body>
    <div class="menu-item">
        <div class="settings-circle">
            <div class="emoji-icon">🔍</div>
        </div>
    </div>
    <script>
        document.querySelector('.menu-item').addEventListener('click', () => {
            require('electron').ipcRenderer.send('menu-item-clicked', 'options');
        });

        require('electron').ipcRenderer.on('fade-in', () => {
            document.body.classList.add('fade-in');
        });

        require('electron').ipcRenderer.on('fade-out', () => {
            document.body.classList.add('fade-out');
        });
    </script>
</body>
</html>`;

  return `data:text/html;base64,${Buffer.from(htmlContent).toString('base64')}`;
}

/**
 * Refresh model information before building menu
 * This function is a hook for refreshing data before showing the menu
 */
function refreshModelInfo() {
  // Since we're now showing all models, this function can be simplified
  logger.model('Refreshing model information before building menu');
  // No need to do anything, but we keep the function as a hook
  // in case we need it in the future
}

module.exports = {
  init,
  initTempDir,
  getImageDataUrl,
  generateCharacterHTML,
  getCharacterFiles,
  generateOptionsHTML,
  refreshModelInfo
}; 