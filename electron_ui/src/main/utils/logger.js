// Improved logging utility for the bitHuman Visual Agent Electron UI
// This provides colorful logs with consistent tagging similar to the daemon package

const chalk = require('chalk');

// Check if colors should be disabled (NO_COLOR environment variable is set)
const noColor = process.env.NO_COLOR !== undefined;

// If colors are disabled, force chalk to disable color
if (noColor) {
  chalk.level = 0;
}

// Log categories with colors optimized for both dark and light mode
const LogCategory = {
  SYSTEM: { name: 'SYSTEM', color: chalk.hex('#4287f5').bold }, // Bright blue
  UI: { name: 'UI', color: chalk.hex('#36c7c7').bold }, // Bright cyan
  MODEL: { name: 'MODEL', color: chalk.hex('#e83e8c').bold }, // Bright magenta
  SERVER: { name: 'SERVER', color: chalk.hex('#28a745').bold }, // Bright green
  NETWORK: { name: 'NETWORK', color: chalk.hex('#ffc107').bold }, // Bright yellow
  ELECTRON: { name: 'ELECTRON', color: chalk.bgHex('#4287f5').hex('#ffffff').bold }, // White on blue background
  DEBUG: { name: 'DEBUG', color: chalk.hex('#adb5bd').bold } // Bright gray
};

/**
 * Format a log message with appropriate styling
 * @param {string} message - The message to log
 * @param {object} category - Category object containing name and color
 * @param {string} level - Log level (INFO, WARN, ERROR, etc.)
 * @returns {string} - Formatted log message
 */
function formatLog(message, category, level) {
  // Use ISO timestamp in local timezone for better readability and consistency
  const timestamp = new Date().toISOString().slice(0, 19).replace('T', ' ');
  const categoryStr = category.color(`[${category.name.padEnd(10)}]`);
  const levelStr = formatLevel(level);
  
  // Use bright white for the timestamp
  return `${chalk.hex('#e0e0e0')(timestamp)} | ${categoryStr} | ${levelStr} | ${message}`;
}

/**
 * Format the log level with appropriate color
 * @param {string} level - Log level
 * @returns {string} - Colored log level
 */
function formatLevel(level) {
  switch(level) {
    case 'ERROR':
      return chalk.hex('#ff5252').bold(`${level.padEnd(7)}`); // Bright red
    case 'WARN':
      return chalk.hex('#ffab40').bold(`${level.padEnd(7)}`); // Bright orange
    case 'INFO':
      return chalk.hex('#ffffff').bold(`${level.padEnd(7)}`); // Bright white
    case 'DEBUG':
      return chalk.hex('#adb5bd').bold(`${level.padEnd(7)}`); // Bright gray
    default:
      return chalk.hex('#ffffff').bold(`${level.padEnd(7)}`); // Bright white
  }
}

/**
 * Log an informational message
 * @param {string} message - Message to log
 * @param {object} category - Log category (from LogCategory)
 */
function info(message, category = LogCategory.SYSTEM) {
  console.log(formatLog(message, category, 'INFO'));
}

/**
 * Log a warning message
 * @param {string} message - Message to log
 * @param {object} category - Log category (from LogCategory)
 */
function warn(message, category = LogCategory.SYSTEM) {
  console.warn(formatLog(message, category, 'WARN'));
}

/**
 * Log an error message
 * @param {string} message - Message to log
 * @param {object} category - Log category (from LogCategory)
 */
function error(message, category = LogCategory.SYSTEM) {
  console.error(formatLog(message, category, 'ERROR'));
}

/**
 * Log a debug message
 * @param {string} message - Message to log
 * @param {object} category - Log category (from LogCategory)
 */
function debug(message, category = LogCategory.DEBUG) {
  console.debug(formatLog(message, category, 'DEBUG'));
}

// Convenience category-specific loggers
const system = (message, level = 'INFO') => {
  const method = getLogMethod(level);
  method(message, LogCategory.SYSTEM);
};

const ui = (message, level = 'INFO') => {
  const method = getLogMethod(level);
  method(message, LogCategory.UI);
};

const model = (message, level = 'INFO') => {
  const method = getLogMethod(level);
  method(message, LogCategory.MODEL);
};

const server = (message, level = 'INFO') => {
  const method = getLogMethod(level);
  method(message, LogCategory.SERVER);
};

const network = (message, level = 'INFO') => {
  const method = getLogMethod(level);
  method(message, LogCategory.NETWORK);
};

const electron = (message, level = 'INFO') => {
  const method = getLogMethod(level);
  method(message, LogCategory.ELECTRON);
};

/**
 * Get the appropriate log method based on level
 * @param {string} level - Log level
 * @returns {Function} - Logging function
 */
function getLogMethod(level) {
  switch(level.toUpperCase()) {
    case 'ERROR': return error;
    case 'WARN': return warn;
    case 'DEBUG': return debug;
    case 'INFO':
    default: return info;
  }
}

// Export the logging functions
module.exports = {
  LogCategory,
  info,
  warn,
  error,
  debug,
  system,
  ui,
  model,
  server,
  network,
  electron
}; 