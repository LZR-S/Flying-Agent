import json


def reply(name, arguments=None, *, frame='frame_000001', call_id='call_test', note=''):
    return {'role':'assistant','content':None,'tool_calls':[
        {'id':call_id,'type':'function','function':{'name':name,
         'arguments':json.dumps(dict(arguments or {},based_on_frame_id=frame,note=note))}}]}


def review_arguments(image_id='shot_000001',status='satisfied'):
    return {'image_id':image_id,'checks':[{'requirement':'test fixture contains a complete red field',
            'status':status,'evidence':'Red pixels reach all four image edges.'}],
            'quality_issues':[] if status=='satisfied' else ['Task compliance is uncertain.'],
            'next_step':'finish','rationale':'Select the visible fixture; no improvement needed in this protocol test.'}
