# bitHuman Visual Agent Desktop App

This example demonstrates how to run a bitHuman Visual Agent desktop application.

## Prerequisites

1. bitHuman API Secret
2. OpenAI API Key
3. Bash-compatible terminal

## System Compatibility

This application has been primarily tested on macOS. Linux and Windows users may need to make some tweaks to get it work.

## Setup Instructions

1. Clone this repository to your local machine.

2. Get API Secret from the [bitHuman website](https://console.bithuman.io/develop).

3. Configure your API keys in the `default_settings.json` file:
   ```json
   {
     "apiKeys": {
       "bithuman": "YOUR_BITHUMAN_API_KEY",
       "openai": "YOUR_OPENAI_API_KEY"
     }
   }
   ```

## Running the Application

To run the bitHuman Visual Agent desktop application:

```bash
bash start.sh
```

## How It Works

This desktop application integrates the bitHuman SDK:

* User interactions are processed through the application
* The bitHuman SDK generates realistic visual agent responses
* Configuration settings can be adjusted in the `default_settings.json` file

For more information about the bitHuman SDK and its capabilities, please visit the [bitHuman documentation](https://docs.bithuman.io).



