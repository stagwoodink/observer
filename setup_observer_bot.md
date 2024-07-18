
# Setting Up Observer Bot

Follow these steps to set up and run the Observer Bot on a new server.

## Prerequisites

1. Ensure you have Python 3.6 or later installed on your server.
2. Install Git to clone the repository.
3. Install MongoDB for logging events.

## Steps

### 1. Clone the Repository

Open your terminal and run the following command to clone the repository:

`git clone <your-repository-url>`

### 2. Navigate to the Project Directory

Change to the project directory:

`cd <repository-directory>`

### 3. Create a Virtual Environment

Run the following commands to create and activate a virtual environment:

`python3 -m venv venv`
`source venv/bin/activate` (on Windows use `venv\Scripts\activate`)

### 4. Install Dependencies

Install the required Python packages using pip:

`pip install -r requirements.txt`

### 5. Configure Environment Variables

Create a `.env` file in the project root directory and add your Discord token:

```
DISCORD_TOKEN=your_discord_token_here
MONGO_URI=your_mongodb_uri_here
```

### 6. Run MongoDB

Make sure your MongoDB server is running. You can start it with the following command:

`mongod --dbpath ~/data/db --bind_ip 127.0.0.1`

### 7. Run the Bot

Start the bot by running the following command:

`python observer_bot.py`

Your Observer Bot should now be up and running!
