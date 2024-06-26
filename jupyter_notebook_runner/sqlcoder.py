from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import torch

from datetime import datetime
from csv_logger import write_log
import constants
import gc


def run(client, ddl, prompts, cache_directory, dataset_name, additional_context=None):
    print('*** Query generation statistics: ***')
    print('Client: ' + client)
    print('Model: ' + 'SQLCoder')
    print('Dataset: ' + dataset_name)


    if client == constants.CPU:
        sqlcoder_model_path = 'defog/sqlcoder-7b-2'
    elif client == constants.GPU_3070:
        sqlcoder_model_path = 'defog/sqlcoder-7b-2'
    elif client == constants.GPU_4090:
        sqlcoder_model_path = 'defog/sqlcoder2'

    tokenizer = AutoTokenizer.from_pretrained(sqlcoder_model_path, cache_dir=cache_directory)

    for i in range(len(prompts)):
        start_time = datetime.now()

        additional_context_prompt = f"""
        This is some additional context about the table structures: \
        {additional_context} \
        \
        """

        prompt = (f"""\
        ### Task \
        Generate a SQL query to answer [QUESTION] {prompts[i]} [/QUESTION] \
        \
        ### Instructions \
        - If you cannot answer the question with the available database schema, return 'I do not know' \
        \
        ### Database Schema \
        The query will run on a database with the following schema: \
        {ddl} \
        \
        {'' if additional_context is None else additional_context_prompt}
        ### Answer \
        Given the database schema, here is the SQL query that answers [QUESTION]{prompts[i]}[/QUESTION] \
        [SQL] \
            """)

        print('Generating response for prompt ' + str(i + 1) + ': ' + prompts[i])

        if client == constants.CPU:
            inputs = tokenizer(prompt, return_tensors="pt")
        elif client[:3] == 'gpu':
            inputs = tokenizer(prompt, return_tensors="pt").to(constants.CUDA)

        model = load_model(client, sqlcoder_model_path, cache_directory)
        
        outputs = model.generate(**inputs, max_length=len(prompt) + 300)
        response = tokenizer.batch_decode(outputs)[0]

        end_time = datetime.now()
        duration = end_time - start_time

        duration = str(duration.total_seconds())
        print('Elapsed time: ' + duration + ' seconds')
        print('Model response:')
        print(response)
        print('')

        write_log('sqlcoder_log.csv', 'a', start_time, client, 'SQLCoder', dataset_name, i, prompts[i], duration, response, False if additional_context is None else True)

        # cleanup
        del model
        gc.collect()
        torch.cuda.empty_cache()

    print('Done processing dataset ' + dataset_name + ' on SQLCoder')
    print('')

def load_model(client, model_path, cache_directory):
    if client == constants.CPU:
        model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.bfloat16, cache_dir=cache_directory)
        pass
    
    elif client == constants.GPU_3070:

        model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.bfloat16, cache_dir = cache_directory).to(constants.CUDA)
 
    elif client == constants.GPU_4090:
        bnb_config = BitsAndBytesConfig(
            load_in_8bit=True,
            llm_int8_enable_fp32_cpu_offload=True 
        )

        model = AutoModelForCausalLM.from_pretrained(model_path, quantization_config=bnb_config, device_map="auto", cache_dir = cache_directory)
    
    return model