from flask import Flask, render_template, request, jsonify, send_file
import tempfile
import os
import re
from difflib import SequenceMatcher
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Your existing BibTeX processing functions (copy from original)
def parse_bib_entries(content):
    """Parse BibTeX content and extract individual entries."""
    entry_pattern = r'@(.*?)((?=@)|$)'
    entries = re.finditer(entry_pattern, content, re.DOTALL)
    
    parsed_entries = []
    for entry in entries:
        entry_text = entry.group(0).strip()
        if entry_text:
            parsed_entries.append(entry_text)
    
    return parsed_entries

def extract_entry_info(entry):
    """Extract key information from a BibTeX entry."""
    match = re.match(r'@(\w+)\s*{\s*([^,]+)', entry)
    if not match:
        return None
    
    entry_type = match.group(1).lower()
    citation_key = match.group(2)
    
    # Extract title
    title_match = re.search(r'title\s*=\s*[{"](.+?)[}"]', entry, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).lower().replace('\n', ' ').replace('\t', ' ') if title_match else ""
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Extract authors
    author_match = re.search(r'author\s*=\s*[{"](.+?)[}"]', entry, re.IGNORECASE | re.DOTALL)
    authors = author_match.group(1) if author_match else ""
    
    # Extract year
    year_match = re.search(r'year\s*=\s*[{"]?(\d{4})[}"]?', entry, re.IGNORECASE)
    year = year_match.group(1) if year_match else ""
    
    # Extract DOI
    doi_match = re.search(r'doi\s*=\s*[{"](.+?)[}"]', entry, re.IGNORECASE)
    doi = doi_match.group(1) if doi_match else ""
    
    return {
        'type': entry_type,
        'citation_key': citation_key,
        'title': title,
        'authors': authors,
        'year': year,
        'doi': doi,
        'full_entry': entry
    }

def find_duplicates(entries_info, similarity_threshold=0.8):
    """Find potential duplicate entries based on similarity."""
    duplicates = []
    processed = set()
    
    # Ensure threshold is a float
    threshold = float(similarity_threshold)
    
    for i, entry1 in enumerate(entries_info):
        if i in processed or entry1 is None:
            continue
            
        group = [i]
        
        # DOI matching first
        if entry1['doi']:
            for j, entry2 in enumerate(entries_info):
                if i == j or j in processed or entry2 is None:
                    continue
                if entry1['doi'] == entry2['doi']:
                    group.append(j)
        
        # Similarity matching for entries without DOI matches
        if len(group) == 1:
            same_year_indices = [j for j, entry2 in enumerate(entries_info) 
                               if entry2 is not None and j != i and j not in processed 
                               and entry2['year'] == entry1['year']]
            
            for j in same_year_indices:
                entry2 = entries_info[j]
                
                if entry1['title'] and entry2['title']:
                    if abs(len(entry1['title']) - len(entry2['title'])) / max(len(entry1['title']), 1) < 0.3:
                        title_similarity = SequenceMatcher(None, entry1['title'], entry2['title']).ratio()
                        if title_similarity > threshold:
                            group.append(j)
                            continue
                
                if j not in group and entry1['authors'] and entry2['authors']:
                    if abs(len(entry1['authors']) - len(entry2['authors'])) / max(len(entry1['authors']), 1) < 0.3:
                        authors_similarity = SequenceMatcher(None, entry1['authors'], entry2['authors']).ratio()
                        if authors_similarity > threshold:
                            group.append(j)
        
        if len(group) > 1:
            duplicates.append(group)
            processed.update(group)
    
    return duplicates

def check_identical_entries(entries_info, group):
    """Check if entries in a group are identical."""
    if not group or len(group) <= 1:
        return False, None
    
    primary_idx = group[0]
    primary_entry = entries_info[primary_idx]
    
    primary_content = {
        'title': primary_entry['title'].lower() if primary_entry['title'] else '',
        'authors': primary_entry['authors'].lower() if primary_entry['authors'] else '',
        'year': primary_entry['year'],
        'doi': primary_entry['doi'].lower() if primary_entry['doi'] else '',
        'type': primary_entry['type'].lower() if primary_entry['type'] else ''
    }
    
    for idx in group[1:]:
        entry = entries_info[idx]
        entry_content = {
            'title': entry['title'].lower() if entry['title'] else '',
            'authors': entry['authors'].lower() if entry['authors'] else '',
            'year': entry['year'],
            'doi': entry['doi'].lower() if entry['doi'] else '',
            'type': entry['type'].lower() if entry['type'] else ''
        }
        
        if primary_content != entry_content:
            return False, None
    
    # Choose entry with shortest citation key
    best_idx = min(group, key=lambda idx: len(entries_info[idx]['citation_key']))
    return True, best_idx

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_file():
    """Analyze uploaded BibTeX file for duplicates."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.bib'):
            return jsonify({'error': 'Please upload a .bib file'}), 400
        
        # Get similarity threshold from form
        threshold = float(request.form.get('threshold', 0.8))
        
        # Read file content
        content = file.read().decode('utf-8')
        
        # Process the file
        entries = parse_bib_entries(content)
        entries_info = [extract_entry_info(entry) for entry in entries]
        valid_entries = [e for e in entries_info if e is not None]
        
        # Find duplicates
        duplicates = find_duplicates(entries_info, threshold)
        
        # Process duplicates - separate identical from non-identical
        identical_groups = []
        manual_groups = []
        auto_resolved = 0
        
        for group in duplicates:
            identical, best_idx = check_identical_entries(entries_info, group)
            if identical:
                auto_resolved += 1
                identical_groups.append({
                    'group': group,
                    'best_idx': best_idx,
                    'citation_key': entries_info[best_idx]['citation_key']
                })
            else:
                # Prepare group info for manual resolution
                group_info = []
                for idx in group:
                    entry = entries_info[idx]
                    if entry:
                        group_info.append({
                            'index': idx,
                            'citation_key': entry['citation_key'],
                            'title': entry['title'],
                            'authors': entry['authors'],
                            'year': entry['year'],
                            'doi': entry['doi'],
                            'type': entry['type'],
                            'full_entry': entry['full_entry']
                        })
                manual_groups.append(group_info)
        
        return jsonify({
            'total_entries': len(entries),
            'valid_entries': len(valid_entries),
            'duplicate_groups': len(duplicates),
            'auto_resolved': auto_resolved,
            'manual_resolution_needed': len(manual_groups),
            'manual_groups': manual_groups,
            'identical_groups': identical_groups,
            'entries_info': entries_info,  # Store for later processing
            'threshold': threshold
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/resolve', methods=['POST'])
def resolve_duplicates():
    """Process a single duplicate group resolution."""
    try:
        data = request.get_json()
        action = data.get('action')
        group_index = int(data.get('group_index', 0))  # Ensure integer
        selected_entry_index = int(data.get('selected_entry_index', 0))  # Ensure integer
        entries_info = data.get('entries_info')
        manual_groups = data.get('manual_groups')
        identical_groups = data.get('identical_groups', [])
        threshold = float(data.get('threshold', 0.8))
        
        # Track resolution state - ensure all keys are strings for consistency
        resolution_state = data.get('resolution_state', {
            'resolved_groups': {},
            'current_group': 0
        })
        
        current_group = int(resolution_state['current_group'])
        resolved_groups = resolution_state.get('resolved_groups', {})
        
        # Handle auto_complete action (when no manual resolution needed)
        if action == 'auto_complete':
            entries_to_keep = []
            
            # Add entries that aren't in any duplicate group
            all_duplicate_indices = set()
            
            # Add auto-resolved identical entries
            for group_info in identical_groups:
                for idx in group_info['group']:
                    all_duplicate_indices.add(idx)
                best_idx = group_info['best_idx']
                entries_to_keep.append(entries_info[best_idx]['full_entry'])
            
            # Add non-duplicate entries
            for i, entry in enumerate(entries_info):
                if entry is None:
                    continue
                if i not in all_duplicate_indices:
                    entries_to_keep.append(entry['full_entry'])
            
            # Generate output file
            output_content = '\n\n'.join(entries_to_keep)
            
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False)
            temp_file.write(output_content)
            temp_file.close()
            
            return jsonify({
                'status': 'complete',
                'message': f'Deduplication complete! Kept {len(entries_to_keep)} entries.',
                'download_url': f'/download/{os.path.basename(temp_file.name)}',
                'original_entries': len([e for e in entries_info if e is not None]),
                'final_entries': len(entries_to_keep)
            })
        
        # Process the current group based on action
        if action == 'keep_selected' and current_group < len(manual_groups):
            group = manual_groups[current_group]
            if 0 <= selected_entry_index < len(group):
                selected_entry = group[selected_entry_index]
                resolved_groups[str(current_group)] = {  # Use string key
                    'action': 'keep_selected',
                    'entry': selected_entry
                }
        
        elif action == 'keep_all' and current_group < len(manual_groups):
            group = manual_groups[current_group]
            resolved_groups[str(current_group)] = {  # Use string key
                'action': 'keep_all',
                'entries': group
            }
        
        elif action == 'skip' and current_group < len(manual_groups):
            resolved_groups[str(current_group)] = {  # Use string key
                'action': 'skip'
            }
        
        # Move to next group
        current_group += 1
        
        # Check if we're done with all groups
        if current_group >= len(manual_groups):
            # Generate final output
            entries_to_keep = []
            
            # Add entries that aren't in any duplicate group
            all_duplicate_indices = set()
            
            # Collect all indices from manual groups
            for group in manual_groups:
                for entry in group:
                    all_duplicate_indices.add(entry['index'])
            
            # Collect all indices from identical groups
            for group_info in identical_groups:
                for idx in group_info['group']:
                    all_duplicate_indices.add(idx)
            
            # Add non-duplicate entries
            for i, entry in enumerate(entries_info):
                if entry is None:
                    continue
                if i not in all_duplicate_indices:
                    entries_to_keep.append(entry['full_entry'])
            
            # Add auto-resolved identical entries
            for group_info in identical_groups:
                best_idx = group_info['best_idx']
                entries_to_keep.append(entries_info[best_idx]['full_entry'])
            
            # Add manually resolved entries
            for group_idx_str, resolution in resolved_groups.items():
                if resolution['action'] == 'keep_selected':
                    entries_to_keep.append(resolution['entry']['full_entry'])
                elif resolution['action'] == 'keep_all':
                    for entry in resolution['entries']:
                        entries_to_keep.append(entry['full_entry'])
                # skip action adds nothing
            
            # Generate output file
            output_content = '\n\n'.join(entries_to_keep)
            
            # Create temporary file for download
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False)
            temp_file.write(output_content)
            temp_file.close()
            
            return jsonify({
                'status': 'complete',
                'message': f'Deduplication complete! Kept {len(entries_to_keep)} entries.',
                'download_url': f'/download/{os.path.basename(temp_file.name)}',
                'original_entries': len([e for e in entries_info if e is not None]),
                'final_entries': len(entries_to_keep)
            })
        
        else:
            # Return next group to resolve
            next_group = manual_groups[current_group]
            return jsonify({
                'status': 'continue',
                'current_group': current_group,
                'total_groups': len(manual_groups),
                'group_data': next_group,
                'resolution_state': {
                    'resolved_groups': resolved_groups,
                    'current_group': current_group
                }
            })
        
    except Exception as e:
        import traceback
        print(f"Error in resolve_duplicates: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download the deduplicated file."""
    try:
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, filename)
        
        if os.path.exists(file_path):
            return send_file(
                file_path,
                as_attachment=True,
                download_name='deduplicated.bib',
                mimetype='text/plain'
            )
        else:
            return jsonify({'error': 'File not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)