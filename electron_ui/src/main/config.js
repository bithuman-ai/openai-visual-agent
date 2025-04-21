// Server configuration for the bitHuman Visual Agent Application
// This file now reads the server port from settings.json

const fs = require('fs');
const path = require('path');
const os = require('os');
const logger = require('./utils/logger');

// Get the user data directory (same logic as in the Python code)
function getUserDataDirectory() {
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

// Read port from settings.json, with fallback to default
let serverPort = 5001; // Default port if settings.json cannot be read
try {
  const settingsPath = path.join(getUserDataDirectory(), 'settings.json');
  if (fs.existsSync(settingsPath)) {
    const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    if (settings && settings.server && settings.server.port) {
      serverPort = settings.server.port;
      logger.server(`Read server port ${serverPort} from settings.json`);
    }
  }
} catch (error) {
  logger.error(`Error reading server port from settings.json: ${error}`, logger.LogCategory.SERVER);
  logger.server(`Using default port: ${serverPort}`);
}

module.exports = {
  // Server port read from settings.json
  SERVER_PORT: serverPort,
  
  // API endpoints
  API_ENDPOINTS: {
    STATUS: '/api/status',
    RELOAD_MODEL: '/api/reload'
  }
};