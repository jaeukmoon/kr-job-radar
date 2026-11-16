import unittest
from degree_requirements import attach_degrees, extract_degrees


class DegreeRequirementsTests(unittest.TestCase):
    def test_korean_sections_and_alternatives(self):
        text = '자격요건\n컴퓨터공학 석사 이상 또는 동등한 실무 경험\n우대사항\n박사 학위 보유자\n전형절차\n서류와 면접'
        result = extract_degrees(text)
        self.assertEqual([x['degree'] for x in result['required']], ['masters'])
        self.assertEqual([x['degree'] for x in result['preferred']], ['phd'])
        self.assertIn('또는 동등한 실무 경험',result['required'][0]['text'])
        self.assertEqual(result['unclassified'], [])

    def test_short_english_sections_are_not_discarded(self):
        result = extract_degrees("Minimum qualifications:\nM.S. or Ph.D.\nPreferred qualifications:\nDoctoral research.")
        self.assertEqual({x['degree'] for x in result['required']}, {'masters','phd'})
        self.assertEqual(result['preferred'][0]['degree'], 'phd')

    def test_masters_spelling_variants(self):
        for text in ["Master's degree", 'Master’s in CS', 'Masters in statistics', 'MSc in AI', 'M.Eng. in EE', 'Master of Science']:
            with self.subTest(text=text):
                self.assertEqual(extract_degrees('Qualifications:\n'+text)['required'][0]['degree'],'masters')

    def test_false_friends_do_not_match_degrees(self):
        result = extract_degrees('Qualifications:\nMaster data management, MS Office, Scrum master, master Python. Physician assistant.')
        self.assertFalse(any(result[key] for key in ('required','preferred','unclassified')))

    def test_body_does_not_become_a_requirement(self):
        result = extract_degrees('Our team includes PhD researchers.\nResponsibilities\nMentor MSc interns.\nQualifications\nPython experience.')
        self.assertFalse(result['required'])
        self.assertFalse(result['preferred'])
        self.assertTrue(result['unclassified'])

    def test_preferred_section_stops_before_benefits(self):
        result = extract_degrees('Preferred qualifications\nPython\nBenefits\nPhD tuition support',
                                 preferred='Preferred qualifications\nPython\nBenefits\nPhD tuition support')
        self.assertFalse(result['preferred'])

    def test_markdown_and_html(self):
        result = extract_degrees('<h3>자격 요건</h3><p>석사/박사</p><h3>우대 사항</h3><p>박사 연구 경험</p>')
        self.assertEqual(len(result['required']),2)
        self.assertEqual(len(result['preferred']),1)

    def test_toss_headers(self):
        result = extract_degrees('# 이런 분과 함께하고 싶어요\n석사 이상\n# 이런 경험이 있다면 더 좋아요\n박사 학위')
        self.assertEqual(result['required'][0]['degree'],'masters')
        self.assertEqual(result['preferred'][0]['degree'],'phd')

    def test_structured_sections_without_headers(self):
        result = extract_degrees('Work on forecasting.\nMaster’s or equivalent experience\nPhD desirable',
                                 required='Master’s or equivalent experience',preferred='PhD desirable')
        self.assertEqual(result['required'][0]['degree'],'masters')
        self.assertEqual(result['preferred'][0]['degree'],'phd')
        self.assertFalse(result['unclassified'])

    def test_missing_text_stays_unknown(self):
        result = extract_degrees('')
        self.assertFalse(result['available'])
        self.assertFalse(any(result[key] for key in ('required','preferred','unclassified')))

    def test_combined_korean_graduate_degrees(self):
        for text in ['석박사 학위', '석·박사 학위', '석/박사 학위']:
            result = extract_degrees('이런 경험이 있다면 더 잘 맞아요\n'+text)
            self.assertEqual({x['degree'] for x in result['preferred']}, {'masters','phd'})

    def test_repeated_posting_sections_stop_before_next_duties(self):
        result = extract_degrees('담당업무\n개발\n자격요건\nPython\n우대사항\nSQL\n담당업무\n박사 연구원 멘토링\n자격요건\nPython\n우대사항\nSQL')
        self.assertFalse(result['required'])
        self.assertFalse(result['preferred'])
        self.assertTrue(result['unclassified'])

    def test_preserves_evidence_beyond_display_and_quals_caps(self):
        text = 'About the role\n'+('Company intro. '*180)+'\nQualifications\n'+('Python experience. '*180)+'\nPhD or equivalent experience.'
        job = {'title':'Researcher','description':'Intro', 'quals':{'required':'Python experience'},
               'scoring_description':text, 'score':73, 'scores':{'overall':73}, 'application_status':'applied'}
        before = dict(job)
        attach_degrees(job)
        self.assertEqual(job['degree_requirements']['required'][0]['degree'],'phd')
        for key in before:
            self.assertEqual(job[key],before[key])

    def test_degree_in_title_alone_not_qualification(self):
        job = {'title':'PhD Research Intern','description':''}
        attach_degrees(job)
        self.assertFalse(job['degree_requirements']['available'])


if __name__ == '__main__':
    unittest.main()
