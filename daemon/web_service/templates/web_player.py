"""HTML template for the web-based video player interface."""

# HTML Template for the web player
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bitHuman Visual Agent</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body {
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: #000;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            width: 100vw;
        }
        #video-container {
            position: relative;
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        #video-feed {
            max-width: 100%;
            max-height: 100%;
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        #stats {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            z-index: 1000;
        }
        .fps-good {
            color: #00ff00;
        }
        .fps-warning {
            color: #ffa500;
        }
        .fps-bad {
            color: #ff0000;
        }
        .exp-good {
            color: #00ff00;
        }
        .exp-warning {
            color: #ffa500;
        }
        .exp-bad {
            color: #ff0000;
        }
        #help-overlay {
            display: none;
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 20px;
            border-radius: 10px;
            z-index: 1000;
            font-family: monospace;
        }
        #help-overlay.visible {
            display: block;
        }
    </style>
</head>
<body>
    <div id="video-container">
        <img id="video-feed" src="" alt="Visual Agent Video Feed">
        <div id="stats">
            FPS: <span id="fps">0</span><br>
            Exp: <span id="exp">0</span>s
        </div>
    </div>
    <div id="help-overlay">
        <h3>Keyboard Shortcuts</h3>
        <div class="help-text">
            <p>Keyboard Shortcuts:</p>
            <p>f - Toggle fullscreen</p>
            <p>d - Toggle debug info</p>
            <p>h - Show/hide this help</p>
            <p>q - Quit application</p>
            <p>Space - Toggle mute</p>
        </div>
    </div>

    <script>
        // Include code to inject server port for Electron
        (function() {
            // This script adds electronConfig to the window when running in Electron
            if (!window.electronConfig) {
                try {
                    // When running in Electron, this might be defined
                    // If not, we'll get the port from environment or origin
                    const serverPort = '{{port}}'; // Will be replaced by Flask
                    window.electronConfig = {
                        SERVER_PORT: parseInt(serverPort) || 5001
                    };
                } catch (e) {
                    console.error('Error setting up electronConfig:', e);
                }
            }
        })();

        const socket = io();
        const videoFeed = document.getElementById('video-feed');
        const fpsElement = document.getElementById('fps');
        const expElement = document.getElementById('exp');
        const statsElement = document.getElementById('stats');
        const helpOverlay = document.getElementById('help-overlay');
        let isDebugVisible = true;

        // Simple way to get the API base URL
        const getApiBaseUrl = () => {
            // First try to get from window.electronConfig (set by Electron app)
            if (window.electronConfig && window.electronConfig.SERVER_PORT) {
                return `http://127.0.0.1:${window.electronConfig.SERVER_PORT}`;
            }

            // If we're in development or running direct from Flask
            return window.location.origin;
        };

        // Toggle functions
        function toggleFullscreen() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen();
            } else {
                document.exitFullscreen();
            }
        }

        function toggleDebug() {
            isDebugVisible = !isDebugVisible;
            statsElement.style.display = isDebugVisible ? 'block' : 'none';
        }

        function toggleHelp() {
            helpOverlay.classList.toggle('visible');
        }

        // Handle incoming frames
        socket.on('frame', function(data) {
            videoFeed.src = 'data:image/jpeg;base64,' + data.frame;

            if (isDebugVisible) {
                // Update FPS with color coding
                fpsElement.textContent = data.fps.toFixed(1);
                fpsElement.className = data.fps >= 20 ? 'fps-good' :
                                     data.fps >= 10 ? 'fps-warning' : 'fps-bad';

                // Update expiration time with color coding
                const expInSeconds = data.exp_time - Date.now() / 1000;
                expElement.textContent = expInSeconds.toFixed(1);
                expElement.className = expInSeconds > 10 ? 'exp-good' :
                                     expInSeconds > 5 ? 'exp-warning' : 'exp-bad';

                statsElement.style.display = 'block';
            } else {
                statsElement.style.display = 'none';
            }
        });

        // Handle keyboard shortcuts
        function handleKeyDown(e) {
            if (e.key === 'f') {
                toggleFullscreen();
            } else if (e.key === 'd') {
                toggleDebug();
            } else if (e.key === 'h') {
                toggleHelp();
            } else if (e.key === ' ') {
                // Space key to toggle mute via API
                e.preventDefault(); // Prevent default space behavior (scrolling)

                // Get API URL from our helper function - use the direct endpoint
                const apiUrl = `${getApiBaseUrl()}/api/direct-toggle-mute`;

                // Use XMLHttpRequest
                const xhr = new XMLHttpRequest();
                xhr.open('POST', apiUrl, true);
                xhr.setRequestHeader('Accept', 'application/json');

                // Handle response
                xhr.onload = function() {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        // Success
                        try {
                            const data = JSON.parse(xhr.responseText);

                            // Show a notification
                            const muteStatus = data.muted ? 'Muted' : 'Unmuted';
                            const notification = document.createElement('div');
                            notification.style.position = 'absolute';
                            notification.style.bottom = '20px';
                            notification.style.left = '20px';
                            notification.style.background = 'rgba(0, 0, 0, 0.7)';
                            notification.style.color = 'white';
                            notification.style.padding = '10px';
                            notification.style.borderRadius = '5px';
                            notification.style.zIndex = '1000';
                            notification.textContent = muteStatus;
                            document.body.appendChild(notification);

                            // Remove notification after 2 seconds
                            setTimeout(() => notification.remove(), 2000);
                        } catch (e) {
                            console.error('Error parsing response:', e);
                        }
                    } else {
                        // Error notification
                        const notification = document.createElement('div');
                        notification.style.position = 'absolute';
                        notification.style.bottom = '20px';
                        notification.style.left = '20px';
                        notification.style.background = 'rgba(255, 0, 0, 0.7)';
                        notification.style.color = 'white';
                        notification.style.padding = '10px';
                        notification.style.borderRadius = '5px';
                        notification.style.zIndex = '1000';
                        notification.textContent = `Error: Request failed`;
                        document.body.appendChild(notification);

                        // Remove notification after 3 seconds
                        setTimeout(() => notification.remove(), 3000);
                    }
                };

                // Handle network errors
                xhr.onerror = function() {
                    // Error notification
                    const notification = document.createElement('div');
                    notification.style.position = 'absolute';
                    notification.style.bottom = '20px';
                    notification.style.left = '20px';
                    notification.style.background = 'rgba(255, 0, 0, 0.7)';
                    notification.style.color = 'white';
                    notification.style.padding = '10px';
                    notification.style.borderRadius = '5px';
                    notification.style.zIndex = '1000';
                    notification.textContent = 'Network error occurred';
                    document.body.appendChild(notification);

                    // Remove notification after 3 seconds
                    setTimeout(() => notification.remove(), 3000);
                };

                // Send the request with no body
                xhr.send();
            }
        }

        // Add our keyboard handler
        document.addEventListener('keydown', handleKeyDown);

        // Hide help overlay after 3 seconds
        let helpTimeout;
        function handleHelpTimeout(e) {
            if (e.key.toLowerCase() === 'h') {
                clearTimeout(helpTimeout);
                helpTimeout = setTimeout(() => {
                    helpOverlay.classList.remove('visible');
                }, 3000);
            }
        }

        document.addEventListener('keydown', handleHelpTimeout);
    </script>
</body>
</html>"""
