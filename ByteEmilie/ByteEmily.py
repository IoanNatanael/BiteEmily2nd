import asyncio
import os
import aiomysql
import discord
from discord.ext import commands
from dotenv import load_dotenv
import datetime
import pytz
from tabulate import tabulate
from collections import defaultdict
import logging

# Load environment variables from a .env file
load_dotenv()

# Initialize Discord bot with specified intents
intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)
countdown_count = 0  # Counter for countdown commands
role_registrations = defaultdict(list)

conn = None  # Global variable for database connection


# Function to check if a user has a specific role
def member_or_trial(user):
    member_role_name = 'member'
    trial_role_name = 'trial'
    lowercase_roles = [role.name.lower() for role in user.roles]
    return any(
        role_name == member_role_name.lower() or role_name == trial_role_name.lower() for role_name in lowercase_roles)


# Function to format a number with hyphens for display
def format_with_hyphens(number):
    if number is None:
        return ""
    return "{:,}".format(number).replace(",", "-").replace(".", ",")


@bot.event
async def on_reaction_add(reaction, user):
    # Check if the reaction is "❌" and the user is not a bot
    if str(reaction.emoji) == "❌" and not user.bot:
        try:
            # Fetch the message to make sure it still exists
            original_message = await reaction.message.channel.fetch_message(reaction.message.id)
            # Check if the message is already deleted
            if original_message is not None:
                # Delete the original message
                await original_message.delete()
            else:
                print("Message not found, could not delete.")
        except discord.NotFound:
            # Handle the case where the message does not exist anymore
            print("Message not found, could not delete.")

    # Check if the reaction is by a bot or on a different server
    elif not user.bot and reaction.message.guild == bot.guilds[0]:
        # Get the role corresponding to the reacted emoji
        new_role = None
        for key, value in emojis.items():
            if value == reaction.emoji:
                new_role = key
                break

        # Remove user from all roles
        for role, members in role_registrations.items():
            if user.name in members:
                role_registrations[role].remove(user.name)

        # Add user to the new role registration dictionary
        if new_role:
            role_registrations[new_role].append(user.name)
            await update_message(reaction.message)


# noinspection PyUnresolvedReferences
async def on_shutdown():
    print("Shutting down...")
    if bot.pool is not None:
        print("Closing connection pool...")
        bot.pool.close()  # Close the connection pool
        await bot.pool.wait_closed()  # Wait until the pool is closed
        print("Connection pool closed.")

        if bot.loop.is_running():
            print("Stopping event loop...")
            bot.loop.stop()  # Stop the event loop if it's still running
            print("Event loop stopped.")
        else:
            print("Event loop is already stopped.")
    else:
        print("Connection pool is already closed.")


# Function to establish a direct connection to the MySQL database
async def create_db_connection():
    try:
        connection = await aiomysql.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT')),
            user=os.getenv('DB_USERNAME'),
            password=os.getenv('DB_PASSWORD'),
            db=os.getenv('DB_DATABASE'),
            autocommit=True,
        )
        return connection
    except Exception as e:
        print("Failed to establish MySQL connection:", e)
        logging.error("Failed to establish MySQL connection: %s", e, exc_info=True)
        return None


# Event handler when the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    bot.connection = await create_db_connection()


# noinspection PyUnresolvedReferences
@bot.command(name="LootBal")
async def lootbal(ctx, playerName: str):
    try:
        # Check if the command is used in the allowed channel
        if ctx.channel.id != 1158534391295905842:
            return

        # Check if the user has the required roles
        if not member_or_trial(ctx.author):
            await ctx.send("You do not have permission to use this command.")
            return
        # Check if the database connection is None
        if bot.connection is None:
            await ctx.send("Database connection is not ready. Please try again later.")
            return

        # Wait until the connection is ready
        async with bot.connection.cursor() as cursor:
            # Execute asynchronous database query to retrieve total amount for the specified player
            await cursor.execute("SELECT SUM(Amount) FROM Transactions WHERE Player = %s", (playerName,))
            result = await cursor.fetchone()

            if result is not None:
                total_amount = result[0]
                formatted_amount = f"{format_with_hyphens(total_amount)} 💰"
                if total_amount == 0 or total_amount is None:
                    formatted_amount = "-0- 💰"
                await ctx.send(f'Player {playerName} has a total amount of {formatted_amount}')
            else:
                await ctx.send('No results found.')

    except Exception as e:
        error_message = f'An error occurred while retrieving the balance: {str(e)}'
        await ctx.send(error_message)  # Send error message to the channel


@bot.command()
async def content_in(ctx, time_str: str):
    if ctx.channel.id != 1005640291937697872:
        return
    else:
        try:
            # Parse input time (hours:minutes)
            hours, minutes = map(int, time_str.split(':'))
            total_seconds = hours * 3600 + minutes * 60

            # Calculate end time in UTC
            current_time = datetime.datetime.utcnow()
            end_time = current_time + datetime.timedelta(seconds=total_seconds)

            # Format countdown message using Discord timestamp format
            utc = pytz.timezone('UTC')
            end_time_utc = utc.localize(end_time)
            discord_timestamp = f'<t:{int(end_time_utc.timestamp())}:R>'
            formatted_time = end_time_utc.strftime('%Y-%m-%d `%H:%M:%S`')
            countdown_message = f"Countdown will end: {discord_timestamp} ({formatted_time} UTC)"

            # Reply to the user's message with the countdown message
            response_message = await ctx.message.reply(countdown_message)

            # Add "❌" emoji reaction to the response message
            await response_message.add_reaction("❌")

            def check_reaction(reaction, user):
                return str(reaction.emoji) == "❌" and reaction.message.id == response_message.id and user == ctx.author

            # Wait for the countdown to finish or until user reacts with "❌" emoji
            while end_time > datetime.datetime.utcnow():
                await asyncio.sleep(1)

                try:
                    reaction, _ = await bot.wait_for("reaction_add", check=check_reaction, timeout=1)
                    # User reacted with "❌", stop the countdown
                    break
                except asyncio.TimeoutError:
                    pass

            # Edit the original countdown message when countdown is done
            await response_message.edit(content="Content ended!")

        except Exception as e:
            await ctx.message.reply(f"Error occurred: {str(e)}")
    pass


# Predefined emojis for each role
emojis = {
    "Main Tank": "🛡️",
    "Off Tank": "⚔️",
    "Main heal": "💊",
    "Party Heal": "🎉",
    "Witchwork": "🧙‍♂️",
    "Weeping": "😢",
    "Basilisk": "🐉",
    "Absence": "🚫",
    "Fill": "✨",
    "delete_message": "❌",
}


@bot.command()
async def setup(ctx, *, args):
    try:
        # Check if the command is sent in the specified channel
        if ctx.channel.id != 1169144302019026954:
            return

        description = args  # Get the user input as the description

        # Create the initial formatted message with the user input as the description
        table_data = []
        for r, emoji in emojis.items():
            table_data.append([f"{emoji} {r}", ''])
        formatted_table = tabulate(table_data, headers=['Role', 'registered'], tablefmt='fancy_grid')

        # Send the initial formatted message as a message with the user input as the description
        message_content = f'_{description}_\n```\n{formatted_table}\n```'
        message = await ctx.send(message_content)

        # Add reactions to the message based on roles
        for role in emojis.values():
            await message.add_reaction(role)

    except Exception as e:
        print(f"An error occurred: {e}")


async def update_message(message):
    # Create a new formatted message with updated registration data using tabulate
    table_data = []
    for r, emoji in emojis.items():
        registered_users = ', '.join(role_registrations.get(r, []))
        table_data.append([f'{emoji} {r}', registered_users])
    formatted_table = tabulate(table_data, headers=['Role', 'registered'], tablefmt='fancy_grid')

    # Edit the message with the updated data
    await message.edit(content=f'_Informative Text_\n```\n{formatted_table}\n```')


# Command to provide information about available commands
@bot.command()
async def info_emily(ctx):
    try:
        if ctx.channel.id != 1005640291937697872 or 1158534391295905842:
            return
        # Create an embed for command information
        embed = discord.Embed(
            title="Command Information",
            description="List of available commands and their explanations:",
            color=discord.Color.gold(),
        )

        # List of command descriptions and usage instructions
        command_s = [
            {
                "name": "**!content_in**",
                "description": " -----------------------------------------------------------------------"
                               "-**Set a countdown** for a specified duration. -----------------------------------------"
                               "-It also shows the final time when the content should happen. -----------"
                               "----------You can also add any text and an image in the message if you want. ----------------"
                               "And you can delete the message by using the '❌' emoji---------------------------"
                               "-The time format is {hh:mm:ss}.",
                "usage": "!content_in <time> [image_url] [additional_text]"
            },
            {
                "name": "**!LootBal**",
                "description": "**Retrieves** the balance amount of the specified player.",
                "usage": "!LootBal <playerName>"
            }
        ]

        # Add fields to the embed for each command
        for command in command_s:
            embed.add_field(
                name=f"☆•☆ {command['name']}",
                value=f"Description: {command['description']}\nUsage: `{command['usage']}`\n{'-' * 80}",
                inline=False
            )

        await ctx.send(embed=embed)  # Send the embed to the channel
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        await ctx.send(error_message)  # Send error message to the channel


# Main function to run the bot
# noinspection PyUnresolvedReferences
def main():
    try:
        # Start the bot with the provided token
        bot.run(os.getenv('BOT_TOKEN'))
    except KeyboardInterrupt:
        print('Bot stopped.')


if __name__ == "__main__":
    main()  # Call the main function if the script is executed directly
