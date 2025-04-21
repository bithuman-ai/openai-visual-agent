// Get configuration
let config = require('../../main/config');

// Function to refresh config to get latest port from settings.json
function refreshConfig() {
    try {
        // Clear require cache
        delete require.cache[require.resolve('../../main/config')];
        // Re-import config
        config = require('../../main/config');
        console.log(`Using server port: ${config.SERVER_PORT}`);
    } catch (error) {
        console.error('Error refreshing config:', error);
    }
}

// We'll manage production/development mode based on settings
let appMode = 'production';

// Function to fetch server mode from settings
async function fetchServerMode() {
    // Refresh config to ensure we have the latest port
    refreshConfig();
    
    try {
        const response = await fetch(`http://localhost:${config.SERVER_PORT}/api/settings`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        if (data && data.server && data.server.mode) {
            appMode = data.server.mode;
            console.log(`Server mode from settings: ${appMode}`);
            if (appMode === 'production') {
                document.body.classList.add('production');
            }
        }
    } catch (error) {
        console.error('Error fetching server mode:', error);
        // Default to development mode on error
        appMode = 'development';
    }
}

// Fetch server mode when socket connects
// For now, default to development mode
// appMode = 'development';

// Refresh config before setting up socket connection
refreshConfig();

// Create a socket.io connection to the server
const socket = io(`http://localhost:${config.SERVER_PORT}`, {
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    transports: ['websocket', 'polling']
});

const videoFeed = document.getElementById('video-feed');
const videoContainer = document.getElementById('video-container');
const helpOverlay = document.getElementById('help-overlay');
let displayMode = 'circle';

// Connection status tracking
let isConnected = false;
let reconnectCount = 0;
let frameCount = 0;
let lastFrameTime = 0;
let lastFrameReceived = 0;
const maxReconnectAttempts = 10;

// Debug message element
const debugMessages = document.createElement('div');
debugMessages.id = 'debug-messages';
debugMessages.style.position = 'fixed';
debugMessages.style.top = '10px';
debugMessages.style.right = '10px';
debugMessages.style.color = 'white';
debugMessages.style.background = 'rgba(0, 0, 0, 0.7)';
debugMessages.style.padding = '10px';
debugMessages.style.borderRadius = '5px';
debugMessages.style.fontSize = '10px';
debugMessages.style.fontFamily = 'monospace';
debugMessages.style.zIndex = '1000';
debugMessages.style.maxWidth = '300px';
debugMessages.style.maxHeight = '150px';
debugMessages.style.overflow = 'auto';
// Only show in development mode
if (appMode === 'development') {
    document.body.appendChild(debugMessages);
}

function addDebugMessage(message) {
    // Only log to console in any environment
    console.log(message);
    
    // But only add to visual debug panel in development
    if (appMode === 'development') {
        const msgElement = document.createElement('div');
        msgElement.textContent = `${new Date().toLocaleTimeString()}: ${message}`;
        debugMessages.appendChild(msgElement);
        // Keep only the last 10 messages
        while (debugMessages.children.length > 10) {
            debugMessages.removeChild(debugMessages.firstChild);
        }
    }
}

// Handle incoming frames
socket.on('frame', function(data) {
    // Don't log frame data to avoid console spam
    
    // Update connection status
    if (!isConnected) {
        addDebugMessage('First frame received, connection established');
        isConnected = true;
        reconnectCount = 0;
        document.body.classList.remove('disconnected');
    }
    
    // Update last frame time
    lastFrameReceived = Date.now();
    
    // Check frame rate - only track it, don't log
    const now = performance.now();
    frameCount++;
    if (lastFrameTime === 0) {
        lastFrameTime = now;
    } else if (now - lastFrameTime > 1000) {
        const fps = Math.round(frameCount * 1000 / (now - lastFrameTime));
        // Silently track FPS without logging
        frameCount = 0;
        lastFrameTime = now;
    }
    
    // Ensure data.frame exists before using it
    if (data.frame) {
        // Update the video feed image
        videoFeed.src = 'data:image/jpeg;base64,' + data.frame;
    }
});

// Handle keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'q' || (e.key === 'Escape' && displayMode !== 'fullscreen')) {
        socket.emit('quit');
        require('electron').ipcRenderer.send('quit');
    } else if (e.key === 'f' || (e.key === 'Escape' && displayMode === 'fullscreen')) {
        // First close any open menu windows
        require('electron').ipcRenderer.send('close-menu');
        
        // Implement the sequence: main circular → square → full screen → main circular
        const videoContainer = document.getElementById('video-container');
        const videoFeed = document.getElementById('video-feed');
        
        // Log current display mode for debugging
        console.log(`Current display mode before transition: ${displayMode}`);
        
        if (displayMode === 'circle') {
            // Step 1: Circle to square (keeping the same size)
            displayMode = 'square';
            console.log('Transitioning from circle to square');
            videoContainer.classList.remove('fullscreen');
            videoFeed.classList.remove('fullscreen');
            
            // Apply square mode classes
            videoContainer.classList.add('square');
            videoFeed.classList.add('square');
            videoContainer.style.borderRadius = '0';
            videoFeed.style.borderRadius = '0';
            
            // Make container and feed fully fill the window
            videoContainer.style.width = '100%';
            videoContainer.style.height = '100%';
            videoFeed.style.width = '100%';
            videoFeed.style.height = '100%';
            
            // Allow window to be resized in square mode
            require('electron').ipcRenderer.send('toggle-shape');
            
            // Start listening for window resize events in square mode
            window.addEventListener('resize', handleSquareModeResize);
            
            // Call resize handler immediately to set initial size
            handleSquareModeResize();
        } else if (displayMode === 'square') {
            // Step 2: Square to fullscreen
            displayMode = 'fullscreen';
            console.log('Transitioning from square to fullscreen');
            
            // Remove square mode classes
            videoContainer.classList.remove('square');
            videoFeed.classList.remove('square');
            
            // Stop listening for resize events in fullscreen mode
            window.removeEventListener('resize', handleSquareModeResize);
            
            // Always send the toggle-shape message to ensure fullscreen is activated
            require('electron').ipcRenderer.send('toggle-shape');
            
            // Delay applying fullscreen classes to ensure the window is in fullscreen mode
            setTimeout(() => {
                if (displayMode === 'fullscreen') {
                    videoContainer.classList.add('fullscreen');
                    videoFeed.classList.add('fullscreen');
                    
                    // Ensure feed fills the entire screen
                    videoFeed.style.width = '100%';
                    videoFeed.style.height = '100%';
                    videoContainer.style.width = '100%';
                    videoContainer.style.height = '100%';
                }
            }, 300);
        } else {
            // Step 3: Fullscreen back to circle
            console.log('Transitioning from fullscreen to circle');
            displayMode = 'circle';
            videoContainer.classList.remove('fullscreen');
            videoFeed.classList.remove('fullscreen');
            videoContainer.classList.remove('square');
            videoFeed.classList.remove('square');
            videoContainer.style.borderRadius = '50%';
            videoFeed.style.borderRadius = '50%';
            
            // Reset to original circle size
            videoFeed.style.width = '270px';
            videoFeed.style.height = '270px';
            videoContainer.style.width = '100%';
            videoContainer.style.height = '100%';
            
            // Stop listening for resize events
            window.removeEventListener('resize', handleSquareModeResize);
            
            // Tell main process to exit fullscreen and restart window
            require('electron').ipcRenderer.send('restart-window');
        }
    } else if (e.key === 'p') {
        // Open settings window
        require('electron').ipcRenderer.send('open-settings');
    } else if (e.key === 'm' && displayMode === 'circle') {
        // Only toggle menu windows in circle mode
        require('electron').ipcRenderer.send('toggle-menu');
    } else if (e.key === 'Escape' && displayMode === 'circle') {
        // Also allow Escape key to close menu in circle mode
        // First close any open menu windows
        require('electron').ipcRenderer.send('close-menu');
    } else if (e.key === 's') {
        // s key minimizes the window
        require('electron').ipcRenderer.send('minimize-window');
    } else if (e.key === ' ' || e.code === 'Space') {
        // Space key triggers mute toggle
        e.preventDefault(); // Prevent default space behavior
        
        // Call the toggleMute function defined in index.html
        if (window.toggleMute && typeof window.toggleMute === 'function') {
            console.log("Space pressed, toggling mute state");
            window.toggleMute(); // Call without any arguments to toggle
        } else {
            console.error("toggleMute function not found in window object");
        }
    } else if (e.key === 'a') {
        // 'a' key toggles between agent and avatar modes
        e.preventDefault();
        
        // Call the toggleMode function defined in index.html
        if (window.toggleMode && typeof window.toggleMode === 'function') {
            window.toggleMode();
        }
    } else if (e.key === 'h') {
        // Toggle help window with h key
        e.preventDefault();
        
        // Send message to main process to toggle help window
        require('electron').ipcRenderer.send('toggle-help-window');
    }
});

// Function to handle window resizing in square mode
function handleSquareModeResize() {
    if (displayMode === 'square') {
        const videoContainer = document.getElementById('video-container');
        const videoFeed = document.getElementById('video-feed');
        
        // Get the current window dimensions
        const windowWidth = window.innerWidth;
        const windowHeight = window.innerHeight;
        
        // Make the video feed fill the entire window
        videoFeed.style.width = `${windowWidth}px`;
        videoFeed.style.height = `${windowHeight}px`;
        
        // Ensure container also fills the entire space
        videoContainer.style.width = '100%';
        videoContainer.style.height = '100%';
        
        console.log(`Window resized in square mode: ${windowWidth}x${windowHeight}, feed filling entire window`);
    }
}

// Add these functions for loading overlay
function showLoadingOverlay() {
    document.getElementById('loading-overlay').style.display = 'flex';
}

function hideLoadingOverlay() {
    document.getElementById('loading-overlay').style.display = 'none';
}

// Connection monitoring
setInterval(() => {
    if (isConnected) {
        // Check if we haven't received frames in 5 seconds
        const now = Date.now();
        if (now - lastFrameReceived > 5000) {
            addDebugMessage('No frames received in 5 seconds. Connection may be stalled.');
            // Only show disconnected state in development mode
            if (appMode === 'development') {
                document.body.classList.add('disconnected');
            }
            isConnected = false;
            
            // Try to reconnect
            addDebugMessage('Attempting to reconnect...');
            socket.disconnect();
            setTimeout(() => {
                socket.connect();
            }, 1000);
        }
    }
}, 5000);

// Listen for loading state changes from main process
require('electron').ipcRenderer.on('loading-state', (event, isLoading) => {
    if (isLoading) {
        showLoadingOverlay();
    } else {
        hideLoadingOverlay();
        // Reconnect WebSocket after model reload
        addDebugMessage('Model loading complete, reconnecting socket');
        socket.disconnect();
        socket.connect();
    }
});

// Listen for model reload status notifications
require('electron').ipcRenderer.on('model-reload-status', (event, data) => {
    if (data.success) {
        addDebugMessage(`Model ${data.characterName} reloaded successfully`);
        // Reconnect WebSocket after successful model reload
        socket.disconnect();
        socket.connect();
        
        // Reset mute indicator to unmuted state since backend resets mute state
        if (window.toggleMute && typeof window.toggleMute === 'function') {
            console.log("Resetting mute state to unmuted after model reload");
            window.toggleMute(false); // Explicitly set to unmuted (false)
        }
        
        // Optionally show a notification
        showTemporaryNotification(`${data.characterName.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')} loaded successfully`);
    } else {
        console.error(`Model reload failed: ${data.error}`);
        // Just log the error, the dialog box is shown by the main process
    }
});

// Function to show a temporary notification
function showTemporaryNotification(message) {
    const notification = document.createElement('div');
    notification.className = 'temporary-notification';
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // Fade in
    setTimeout(() => {
        notification.classList.add('visible');
    }, 10);
    
    // Remove after delay
    setTimeout(() => {
        notification.classList.remove('visible');
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 500); // Wait for fade out animation
    }, 3000);
}

// Add WebSocket connection status monitoring
socket.on('connect', () => {
    addDebugMessage('Connected to server');
    document.body.classList.remove('disconnected');
    
    // Refresh config to ensure we have the latest port from settings.json
    refreshConfig();
    
    // Send a message to the server to verify the connection
    socket.emit('log_message', {
        type: 'info',
        message: 'Electron WebSocket client connected',
        details: {
            url: `http://localhost:${config.SERVER_PORT}`,
            timestamp: new Date().toISOString()
        }
    });

    // Fetch server mode
    fetchServerMode();

    // Check model status immediately after connecting
    fetch(`http://localhost:${config.SERVER_PORT}/api/status`)
        .then(response => response.json())
        .then(data => {
            addDebugMessage('Model status: ' + JSON.stringify(data));
            // If model is ready and not reloading, hide loading overlay
            if (data.is_ready && !data.is_reloading) {
                hideLoadingOverlay();
            }
        })
        .catch(error => {
            addDebugMessage('Error checking model status: ' + error.message);
        });
});

// Add direct socket.io handler for loading state
socket.on('loading-state', (isLoading) => {
    console.log('Received loading state via socket.io:', isLoading);
    if (isLoading) {
        showLoadingOverlay();
    } else {
        hideLoadingOverlay();
    }
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    document.body.classList.add('disconnected');
    isConnected = false;
    
    // Auto reconnect if connection is lost and we haven't exceeded max attempts
    if (reconnectCount < maxReconnectAttempts) {
        reconnectCount++;
        console.log(`Attempting to reconnect (${reconnectCount}/${maxReconnectAttempts})...`);
        setTimeout(() => {
            socket.connect();
        }, 1000 * reconnectCount); // Exponential backoff
    } else {
        console.error('Max reconnect attempts reached');
        showTemporaryNotification('Connection to server lost. Please restart the application.');
    }
});

socket.on('connect_error', (error) => {
    console.error('Connection error:', error);
    document.body.classList.add('disconnected');
    
    // Auto reconnect on error with backoff
    if (reconnectCount < maxReconnectAttempts) {
        reconnectCount++;
        console.log(`Connection error. Attempting to reconnect (${reconnectCount}/${maxReconnectAttempts})...`);
        setTimeout(() => {
            socket.connect();
        }, 1000 * reconnectCount); // Exponential backoff
    } else {
        console.error('Max reconnect attempts reached');
        showTemporaryNotification('Cannot connect to server. Please restart the application.');
    }
});

// Handle fade transitions
require('electron').ipcRenderer.on('fade-out', () => {
    document.body.classList.add('fade-out');
});

require('electron').ipcRenderer.on('fade-in', () => {
    document.body.classList.remove('fade-out');
    document.body.classList.add('fade-in');
    setTimeout(() => {
        document.body.classList.remove('fade-in');
    }, 300);
});

// Listen for fullscreen mode entered confirmation
require('electron').ipcRenderer.on('fullscreen-entered', () => {
    console.log('Fullscreen mode activated');
    
    // Ensure we apply fullscreen styling
    if (displayMode === 'fullscreen') {
        const videoContainer = document.getElementById('video-container');
        const videoFeed = document.getElementById('video-feed');
        videoContainer.classList.add('fullscreen');
        videoFeed.classList.add('fullscreen');
    }
});

// Listen for window restart notification
require('electron').ipcRenderer.on('window-restarted', () => {
    console.log('Window successfully restarted');
    
    // Ensure displayMode is set to circle
    displayMode = 'circle';
    
    // Remove any fullscreen or square classes that might be present
    const videoContainer = document.getElementById('video-container');
    const videoFeed = document.getElementById('video-feed');
    if (videoContainer) {
        videoContainer.classList.remove('fullscreen');
        videoContainer.classList.remove('square');
        videoContainer.style.borderRadius = '50%';
        videoContainer.style.width = '100%';
        videoContainer.style.height = '100%';
    }
    if (videoFeed) {
        videoFeed.classList.remove('fullscreen');
        videoFeed.classList.remove('square');
        videoFeed.style.borderRadius = '50%';
        videoFeed.style.width = '270px';
        videoFeed.style.height = '270px';
        videoFeed.style.objectFit = 'cover';
        videoFeed.style.objectPosition = 'center center';
    }
    
    // Stop listening for resize events in circle mode
    window.removeEventListener('resize', handleSquareModeResize);
});

// Listen for server messages
socket.on('server_message', (data) => {
    console.log('Received server message:', data);
});

// Listen for log receipt confirmations
socket.on('log_receipt', (data) => {
    console.log('Server confirmed receipt of log message:', data);
});

// Allow right-click on the body only in circle mode
document.body.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    if (displayMode === 'circle') {
        require('electron').ipcRenderer.send('show-context-menu');
    }
    // No custom context menu for other modes
});

// Show loading overlay by default when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, showing initial loading overlay');
    showLoadingOverlay();
}); 