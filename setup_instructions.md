# Setup Instructions for Observer Bot

These instructions will guide you through setting up the Observer Bot on a new server using the command line on a Linux system.

## Prerequisites

Before you begin, ensure you have the following:

1. A GitHub account
2. An internet connection
3. Basic knowledge of using a terminal/command prompt

## Step 1: Install Git

1. Open Terminal and run:
```sh
sudo apt-get update
sudo apt-get install git
```

## Step 2: Install Python

1. Open Terminal and run:
```sh
sudo apt-get install python3 python3-venv python3-pip
```

## Step 3: Install MongoDB

1. Open Terminal and run the following commands:
```sh
sudo apt-get update
sudo apt-get install -y mongodb
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

## Step 4: Clone the Repository

1. Open Terminal.
2. Navigate to the directory where you want to clone the repository.
3. Run the following command:
```sh
git clone https://github.com/xandrsgit/observer-bot.git
cd observer-bot
```

## Step 5: Set Up a Virtual Environment

1. In the terminal, navigate to the `observer-bot` directory if you're not already there.
2. Create a virtual environment by running:
```sh
python3 -m venv venv
```

3. Activate the virtual environment:
```sh
source venv/bin/activate
```

## Step 6: Install Dependencies

1. With the virtual environment activated, run:
```sh
pip install -r requirements.txt
```

## Step 7: Configure Environment Variables

1. Create a `.env` file in the `observer-bot` directory.
2. Add the following lines to the `.env` file:
```
DISCORD_TOKEN=your_discord_token_here
MONGO_URI=mongodb://localhost:27017/
```

    Replace `your_discord_token_here` with your actual Discord bot token.

## Step 8: Run the Bot

1. Ensure the virtual environment is activated.
2. Start the bot by running:
```sh 
python observer.py
```

Your Observer Bot should now be up and running!

If you encounter any issues or need further assistance, please refer to the official documentation or seek help from the community.
