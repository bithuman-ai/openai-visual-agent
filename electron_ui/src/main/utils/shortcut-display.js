/**
 * Module for displaying keyboard shortcuts in the terminal
 */
const chalk = require('chalk');

/**
 * Display keyboard shortcuts in the terminal in a nicely formatted panel
 */
function displayShortcuts() {
  const border = chalk.cyan('━'.repeat(80));
  const title = chalk.bold.cyan('ELECTRON UI KEYBOARD SHORTCUTS');
  const horizontalLine = chalk.dim.cyan('─'.repeat(78));
  
  // Define the exact shortcuts specified by the user
  const shortcuts = [
    { key: 'm', icon: '👤', description: 'Character menu' },
    { key: 'p', icon: '⚙️', description: 'Settings' },
    { key: 'a', icon: '🔄', description: 'Toggle avatar mode' },
    { key: 'f', icon: '🖥️', description: 'Fullscreen' },
    { key: 'space', icon: '🔊', description: 'Mute/Unmute' },
    { key: 's', icon: '👇', description: 'Minimize' },
    { key: 'h', icon: '💡', description: 'Toggle help' },
    { key: 'q', icon: '🚪', description: 'Quit app' }
  ];

  // Build and display the shortcuts panel
  console.log('\n' + border);
  console.log(centerText(title, 80));
  console.log(border);
  
  // Display all shortcuts in a grid layout (2 columns)
  console.log(chalk.bold.yellow('Keyboard Controls'));
  
  // Create rows with 2 shortcuts per row
  for (let i = 0; i < shortcuts.length; i += 2) {
    const first = shortcuts[i];
    const second = i + 1 < shortcuts.length ? shortcuts[i + 1] : null;
    
    const firstPart = `  ${chalk.bold.white(first.key.padEnd(8))} ${first.icon}  ${chalk.white(first.description.padEnd(20))}`;
    let secondPart = '';
    
    if (second) {
      secondPart = `  ${chalk.bold.white(second.key.padEnd(8))} ${second.icon}  ${chalk.white(second.description)}`;
    }
    
    console.log(`${firstPart}${secondPart}`);
  }
  
  // Add a separate section for terminal controls
  console.log(horizontalLine);
  console.log(chalk.bold.cyan('Terminal Controls ') + chalk.dim.cyan('(separate from UI)'));
  console.log(`  ${chalk.bold.white('Ctrl+b [')}    Enter scroll mode in tmux`);
  console.log(`  ${chalk.bold.white('Ctrl+b ←/→')}  Switch between tmux panes`);
  console.log(`  ${chalk.bold.white('Ctrl+b d')}    Detach from tmux (app keeps running)`);
  console.log(`  ${chalk.bold.white('Ctrl+c')}      Force quit current process`);
  
  console.log(border);
  console.log(centerText(chalk.dim('Starting application...'), 80));
  console.log('');
}

/**
 * Center text within a given width
 * @param {string} text - The text to center
 * @param {number} width - The total width
 * @returns {string} - Centered text
 */
function centerText(text, width) {
  const textLength = text.replace(/\u001b\[\d+m/g, '').length; // Remove ANSI color codes for length calculation
  const padding = Math.max(0, Math.floor((width - textLength) / 2));
  return ' '.repeat(padding) + text;
}

module.exports = {
  displayShortcuts
}; 