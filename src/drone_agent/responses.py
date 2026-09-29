"""Stateless Responses wire adapter for the existing public tool transcript."""
import copy


class ResponsesAdapter:
    def __init__(self):
        self.outputs={}

    def request(self, model, messages, tools):
        inputs=[]
        for message in messages:
            calls=message.get('tool_calls') or []
            if calls:
                identities=tuple(call['id'] for call in calls)
                inputs.extend(copy.deepcopy(self.outputs[identities]))
            elif message['role']=='tool':
                inputs.append({'type':'function_call_output','call_id':message['tool_call_id'],
                               'output':message['content']})
            else:
                content=message['content']
                if isinstance(content,list):
                    content=[{'type':'input_text','text':part['text']} if part['type']=='text' else
                             {'type':'input_image','image_url':part['image_url']['url']} for part in content]
                inputs.append({'role':message['role'],'content':content})
        functions=[]
        for tool in copy.deepcopy(tools):
            function=tool['function']
            if function['name']=='act':function['parameters'].pop('oneOf')
            functions.append(dict(type='function',**function,strict=False))
        return {'model':model,'input':inputs,'tools':functions,'tool_choice':'auto',
                'parallel_tool_calls':False,'reasoning':{'effort':'medium'},
                'store':False,'include':['reasoning.encrypted_content']}

    def message(self, body):
        output=body.get('output',[])
        calls=[{'id':item['call_id'],'type':'function','function':{
                    'name':item['name'],'arguments':item['arguments']}}
               for item in output if item['type']=='function_call']
        text=''.join(part['text'] for item in output if item['type']=='message'
                     for part in item.get('content',[]) if part['type']=='output_text')
        message={'role':'assistant','content':text or None}
        if calls:
            message['tool_calls']=calls
            self.outputs.setdefault(tuple(call['id'] for call in calls),copy.deepcopy(output))
        return message

    @staticmethod
    def usage(body):
        usage=body.get('usage')
        if usage is None:return None
        return {'prompt_tokens':usage.get('input_tokens'),'completion_tokens':usage.get('output_tokens'),
                'total_tokens':usage.get('total_tokens'),
                'prompt_tokens_details':usage.get('input_tokens_details'),
                'completion_tokens_details':usage.get('output_tokens_details')}
