import re
path = r'e:\SSB -2\NF\Gradesense-01\GradeSense1-main\backend\app\services\annotation_v2\annotator.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

if '# MODULE INTERFACE START' not in code:
    sync_fs = re.findall(r'^def ([a-zA-Z_]\w*)\(', code, re.MULTILINE)
    async_fs = re.findall(r'^async def ([a-zA-Z_]\w*)\(', code, re.MULTILINE)
    all_funcs = sync_fs + async_fs
    
    interface_lines = ['\n\n# MODULE INTERFACE START']
    for f in all_funcs:
        if f.startswith('_'):
            public_name = f[1:]
            interface_lines.append(f'{public_name} = {f}')
            
    interface_lines.append('__all__ = [')
    for f in all_funcs:
        public_name = f[1:] if f.startswith('_') else f
        interface_lines.append(f'    "{public_name}",')
    interface_lines.append(']')
    interface_lines.append('# MODULE INTERFACE END\n')
    
    code = code.rstrip() + '\n' + '\n'.join(interface_lines)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)

print('Updated annotator.py successfully')
