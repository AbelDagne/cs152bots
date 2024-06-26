# bot.py
import discord
from discord.ext import commands
import os
import json
import logging
import re
from constants import UserResponse
from image_flagger import flag_image
import requests
from report import Report
from mod import ModReview
import pdb

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'tokens.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']


class ModBot(discord.Client):
    def __init__(self): 
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = None
        self.mod_channels = {}  # Map from guild to the mod channel id for that guild
        self.reports = {}  # Map from user IDs to the state of their report
        self.reviews = {}  # Map from user IDs to the state of their review
        self.report_history = {}  # Map user IDs to number of successful reports
        self.review_author = None  # Prevents accidental responses by bot in mod_channel
        self.active_review = {}  

    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel
        

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return
        
        # Handle image attachments
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    image_url = attachment.url
                    result = flag_image(image_url)
                    content = result['choices'][0]['message']['content']
                    flagged = "yes" in content.lower()
                    reason = content.split("reason: ")[1] if "reason: " in content else "No specific reason provided."
                    
                    abuse_type, specific_issue, source = 5, 4, "none"  # default values
                    print(result)
                   # Parse detailed response
                    if flagged:
                        parts = content.split("\n")
                        for part in parts:
                            part = part.strip()
                            if part.startswith("1. Abuse type"):
                                try:
                                    abuse_type = int(re.findall(r'\d+', part)[0])
                                except (IndexError, ValueError):
                                    abuse_type = 5  # Default to other
                            elif part.startswith("2. Specific issue"):
                                try:
                                    specific_issue = int(re.findall(r'\d+', part)[0])
                                except (IndexError, ValueError):
                                    specific_issue = 4  # Default to other
                            elif part.startswith("3. Source"):
                                source = part.split("Source: ")[1].strip() if "Source: " in part else "none"

                        await self.handle_flagged_image(message, reason, abuse_type, specific_issue, source)
                    return


        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        # Handle a help message
        if message.content == Report.HELP_KEYWORD:
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        author_dm_channel = message.channel
        responses = []

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reports[author_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():            
            # From here, send it to mod 
            report_info = self.reports[author_id].user_responses 
            report_channel = self.reports[author_id].message.channel
            await self.handle_message_review(self.reports[author_id].message, report_info, author_dm_channel, report_channel)

            self.reports.pop(author_id)        

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        # If it's sent in the mod channel then we can handle it as review
        if message.channel.name == f'group-{self.group_num}-mod' and self.review_author is not None:
            await self.handle_message_review(message, *self.active_review[self.review_author])
            return 
        elif not message.channel.name == f'group-{self.group_num}':
            return

        # Forward the message to the mod channel

        # TODO: uncomment before next milestone
        # mod_channel = self.mod_channels[message.guild.id]
        # await mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        # scores = self.eval_text(message.content)
        # await mod_channel.send(self.code_format(scores))
  
    async def handle_message_review(self, message, report_info, author_dm_channel, group_channel):
        author_id = message.author.id
        responses = []
        mod_channel = self.mod_channels[message.guild.id]

        # If we don't currently have an active review for this user, add one
        if author_id not in self.reviews:
            self.reviews[author_id] = ModReview(self, report_info, message, self.report_history, author_dm_channel, group_channel)
            self.active_review[author_id] = (report_info, author_dm_channel, group_channel)
            self.review_author = author_id

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reviews[author_id].handle_message(message)
        for r in responses:
            await mod_channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reviews[author_id].review_complete():            
            self.reviews.pop(author_id) 
            self.active_review.pop(author_id)
            self.review_author = None

    async def handle_flagged_image(self, message, reason, abuse_type, specific_issue, source):
        author_id = message.author.id
        author_dm_channel = message.channel
        responses = []

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        # Create a new report for the flagged image
        report_info = {
            "reporter": 'auto',
            "image_url": message.attachments[0].url,
            "reason": reason,
            UserResponse.ABUSE_TYPE: abuse_type,  # Misleading or False Information
            UserResponse.SPEC_ISSUE: specific_issue,  # Political Disinformation
            UserResponse.SOURCE: source
        }
        self.reports[author_id].user_responses = report_info

        # Forward the message to the mod channel for review
        await self.handle_message_review(message, report_info, author_dm_channel, author_dm_channel)
        self.reports.pop(author_id)
    
    def eval_text(self, message):
        ''''
        TODO: Once you know how you want to evaluate messages in your channel, 
        insert your code here! This will primarily be used in Milestone 3. 
        '''
        scores = {
            "spam": 0.1,
            "offensive": 0.3,
            "political": 0.8
        }
        return scores

    
    def code_format(self, text):
        ''''
        TODO: Once you know how you want to show that a message has been 
        evaluated, insert your code here for formatting the string to be 
        shown in the mod channel. 
        '''
        return "Evaluated: '" + text+ "'"


client = ModBot()
client.run(discord_token)