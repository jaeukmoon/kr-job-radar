import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import json
import fetch_jobs as jobs
import fetch_details as details


def notice(sn, title='AI 연구개발', **fields):
    return {'recruitNoticeSn':sn,'recruitNoticeName':title,
            'recruitSectorList':[{'recruitSectorName':'데이터 분석'}],
            'company':'KT','receiveEndDatetime':'2026-12-31 23:59:59',
            'recruitNoticeUrl':f'https://kt.recruiter.co.kr/career/jobs/{sn}',
            'isInProgress':True,'isTimeOver':False,**fields}


class KTSourceTests(unittest.TestCase):
    def test_listing_uses_current_public_api_parameters(self):
        with patch.object(jobs,'get_json',return_value={'isSuccess':True,'data':[notice(242664)]}) as read:
            result=jobs.fetch_kt()
        self.assertEqual(read.call_args.args[0],
            'https://recruit.kt.com/api/recruit?currentPage=1&pageSize=100&isInProgress=true&isContainsContents=false')
        self.assertEqual(result[0]['id'],'kt:242664')
        self.assertEqual(result[0]['deadline'],'2026-12-31')

    def test_expired_and_non_ai_roles_do_not_reappear_as_new_jobs(self):
        payload={'isSuccess':True,'data':[notice(1),notice(2,isTimeOver=True),
                 notice(3,title='회계',recruitSectorList=[{'recruitSectorName':'재무회계'}])]}
        with patch.object(jobs,'get_json',return_value=payload):
            self.assertEqual([j['id'] for j in jobs.fetch_kt()],['kt:1'])

    def test_declared_failure_and_malformed_data_fail_closed(self):
        for payload in [{'isSuccess':False,'data':[]},{'isSuccess':True},
                        {'isSuccess':True,'data':None},{'data':[]}]:
            with self.subTest(payload=payload),patch.object(jobs,'get_json',return_value=payload):
                with self.assertRaises(ValueError):jobs.fetch_kt()

    def test_pagination_is_complete_and_repeated_pages_fail_closed(self):
        page=[notice(i) for i in range(100)]
        with patch.object(jobs,'get_json',side_effect=[{'isSuccess':True,'data':page},
                   {'isSuccess':True,'data':[notice(100)]}]) as read:
            self.assertEqual(len(jobs.fetch_kt()),101)
            self.assertIn('currentPage=2',read.call_args.args[0])
        with patch.object(jobs,'get_json',side_effect=[{'isSuccess':True,'data':page}]*2):
            with self.assertRaises(ValueError):jobs.fetch_kt()

    def test_detail_query_uses_same_current_api_with_contents(self):
        payload={'isSuccess':True,'data':[notice(242664,contents='<h3>자격요건</h3><p>석사 이상</p><h3>우대사항</h3><p>박사 학위</p>')]}
        with patch.object(jobs,'get_json',return_value=payload) as read:
            result=details.bulk_kt([])
        self.assertIn('isContainsContents=true',read.call_args.args[0])
        self.assertIn('석사',result['kt:242664'][0])
        self.assertIn('박사',result['kt:242664'][1])

    def test_failed_source_is_not_advertised_as_successful(self):
        def fail():raise RuntimeError('upstream unavailable')
        with tempfile.TemporaryDirectory() as tmp,patch.object(jobs,'DATA',Path(tmp)), \
                patch.object(jobs,'SOURCES',{'kt':fail,'naver':lambda:[]}),patch('sys.argv',['fetch_jobs.py']):
            jobs.main()
            result=json.loads((Path(tmp)/'jobs.json').read_text())
        self.assertEqual(result['sources_ok'],['naver'])
        self.assertEqual(len(result['errors']),1)

    def test_all_sources_failed_preserves_the_previous_snapshot(self):
        def fail():raise RuntimeError('upstream unavailable')
        with tempfile.TemporaryDirectory() as tmp,patch.object(jobs,'DATA',Path(tmp)), \
                patch.object(jobs,'SOURCES',{'kt':fail}),patch('sys.argv',['fetch_jobs.py']):
            path=Path(tmp)/'jobs.json'
            original=json.dumps({'generated':'2026-11-12','jobs':[]})
            path.write_text(original)
            with self.assertRaises(SystemExit):jobs.main()
            self.assertEqual(path.read_text(),original)


if __name__=='__main__':unittest.main()
