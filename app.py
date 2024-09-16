import os
from dotenv import load_dotenv
import chainlit as cl
import openai
import asyncio
import json
from datetime import datetime
from prompts import ASSESSMENT_PROMPT, SYSTEM_PROMPT_1, SYSTEM_PROMPT_2, ADDITIONAL_CONTEXT
import requests
from bs4 import BeautifulSoup
#from student_record import read_student_record, write_student_record, format_student_record, parse_student_record

from langsmith import traceable
from langsmith.wrappers import wrap_openai

# Load environment variables
load_dotenv()

configurations = {
    "mistral_7B_instruct": {
        "endpoint_url": os.getenv("MISTRAL_7B_INSTRUCT_ENDPOINT"),
        "api_key": os.getenv("RUNPOD_API_KEY"),
        "model": "mistralai/Mistral-7B-Instruct-v0.2"
    },
    "mistral_7B": {
        "endpoint_url": os.getenv("MISTRAL_7B_ENDPOINT"),
        "api_key": os.getenv("RUNPOD_API_KEY"),
        "model": "mistralai/Mistral-7B-v0.1"
    },
    "openai_gpt-4": {
        "endpoint_url": os.getenv("OPENAI_ENDPOINT"),
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-3.5-turbo"
    }
}

# Choose configuration
config_key = "openai_gpt-4"
# config_key = "mistral_7B_instruct"
#config_key = "mistral_7B"

# Get selected configuration
config = configurations[config_key]

# Initialize the OpenAI async client
client = wrap_openai(openai.AsyncClient(api_key=config["api_key"], base_url=config["endpoint_url"]))

gen_kwargs = {
    "model": config["model"],
    "temperature": 0.3,
    "max_tokens": 500
}

# Configuration setting to enable or disable the system prompt
ENABLE_SYSTEM_PROMPT = True
ENABLE_ADDITIONAL_CONTEXT = True

def url_to_text(web_url):
    response = requests.get(web_url)
    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse the HTML content of the page
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract all text from the parsed HTML
        text = soup.get_text(separator=' ', strip=True)
        #print(text)
        return text
    else:
        return f"Failed to retrieve content. Status code: {response.status_code}"

URL_OLD="https://www.gutenberg.org/cache/epub/221/pg221.txt"
URL_ONE="https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2025"
full_story_text = url_to_text(URL_ONE)

@traceable
def get_latest_user_message(message_history):
    # Iterate through the message history in reverse to find the last user message
    for message in reversed(message_history):
        if message['role'] == 'user':
            return message['content']
    return None

@traceable
async def assess_message(message_history):
    #file_path = "student_record.md"
    #markdown_content = read_student_record(file_path)
    #parsed_record = parse_student_record(markdown_content)

    latest_message = get_latest_user_message(message_history)

    # Remove the original prompt from the message history for assessment
    filtered_history = [msg for msg in message_history if msg['role'] != 'system']

    # Convert message history, alerts, and knowledge to strings
    history_str = json.dumps(filtered_history, indent=4)
    #alerts_str = json.dumps(parsed_record.get("Alerts", []), indent=4)
    #knowledge_str = json.dumps(parsed_record.get("Knowledge", {}), indent=4)
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    print("Assessment is still TBD.")

   
@traceable
def test_func(inp_msg):
    return "output values"

@traceable
def parse_assessment_output(output):
    try:
        parsed_output = json.loads(output)
        new_alerts = parsed_output.get("new_alerts", [])
        knowledge_updates = parsed_output.get("knowledge_updates", [])
        return new_alerts, knowledge_updates
    except json.JSONDecodeError as e:
        print("Failed to parse assessment output:", e)
        return [], []


@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Summarize Q2 results for NVIDIA",
            message="Can you summarize this quarter's results ? ",
            ),

        cl.Starter(
            label="Revenue breakdown",
            message="What were the major product categories that contributed significantly to the revenue ?",
            ),
        cl.Starter(
            label="Projections",
            message="What are the expectations for the next quarter ?",
            ),
        cl.Starter(
            label="Assessment",
            message="How good or bad was this quarter ?",
            )
        ]

@traceable
@cl.on_message
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    if ENABLE_SYSTEM_PROMPT and (not message_history or message_history[0].get("role") != "system"):
        system_prompt_content = SYSTEM_PROMPT_2
        if ENABLE_ADDITIONAL_CONTEXT:
            story_prompt = ADDITIONAL_CONTEXT.format(input_story=full_story_text)
            print(story_prompt)
            system_prompt_content += "\n" + story_prompt
        message_history.insert(0, {"role": "system", "content": system_prompt_content})

    message_history.append({"role": "user", "content": message.content})
    print("Message history: " + str(message_history))

    asyncio.create_task(assess_message(message_history))
    
    response_message = cl.Message(content="")
    await response_message.send()

    if config_key == "mistral_7B":
        stream = await client.completions.create(prompt=message.content, stream=True, **gen_kwargs)
        async for part in stream:
            if token := part.choices[0].text or "":
                await response_message.stream_token(token)
    else:
        stream = await client.chat.completions.create(messages=message_history, stream=True, **gen_kwargs)
        async for part in stream:
            if token := part.choices[0].delta.content or "":
                await response_message.stream_token(token)

    message_history.append({"role": "assistant", "content": response_message.content})
    cl.user_session.set("message_history", message_history)
    await response_message.update()


if __name__ == "__main__":
    cl.main()
