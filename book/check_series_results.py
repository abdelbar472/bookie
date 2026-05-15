#!/usr/bin/env python
import json

data = json.load(open('v4_test_results.json', encoding='utf-8'))
tests = data['results']

print('=' * 80)
print('SERIES ENRICHMENT TEST SUMMARY')
print('=' * 80)

series_tests = [t for t in tests if 'Series:' in t.get('test', '')]
for test in series_tests:
    status = 'PASS' if test['success'] else 'FAIL'
    books = len(test.get('response', {}).get('results', [{}])[0].get('books', []))
    author = test.get('response', {}).get('results', [{}])[0].get('primary_author', '?')
    print(f'[{status:4}] {test["test"]:40} | Author: {author:20} | Books: {books}')

print()
print('Overall Success Rate:', f'{data["successful"]}/{data["total_tests"]}')
print('Series Tests Passing:', f'{sum(1 for t in series_tests if t["success"])}/5')

