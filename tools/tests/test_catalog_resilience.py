"""Regression tests for nonempty but incomplete Resolve exports and selection."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import controller as module

def item(name,uid):return {'label':name,'value':name,'mediaId':uid}
def catalog(accepted=(),covered=(),generators=0):
    return {'ids':set(accepted),'names':set(),'coveredIds':set(covered),'coveredNames':set(),
        'generators':generators,'rejected':generators-len(accepted)}

class CatalogResilienceTests(unittest.TestCase):
    def make_cache(self,path,items):
        def call(payload,timeout):
            return {'GetTimelineInfo':{'projectName':'PROJECT_TEST'},'GetTemplates':items,
                'GetTemplateScanStatus':{'complete':True,'projectKey':'project-test-id','count':14031,'total':14031},
                'ExportTemplateCatalog':{'exported':True,'projectKey':'project-test-id','files':[]}}[payload['func']]
        cache=module.TemplateCache(path,call);cache.active='PROJECT_TEST'
        cache.projects={'PROJECT_TEST':{'complete':True,'templates':[{'label':'Viejo','value':'Viejo'}]}}
        return cache

    def test_nonempty_export_of_unrelated_adjustments_recovers_textplus(self):
        with tempfile.TemporaryDirectory() as folder:
            items=[item('Text+ personalizado','title-id'),item('Text+ ajuste renombrado','adjust-id')]
            cache=self.make_cache(Path(folder)/'cache.json',items)
            exported=catalog(covered=('foreign-adjust-id',),generators=600)
            library=catalog(accepted=('title-id',),covered=('title-id','adjust-id'),generators=2)
            with patch.object(module,'inspect_catalog',return_value=exported),patch.object(module,'inspect_local_library',return_value=library) as reader:
                cache.scan()
            self.assertEqual(reader.call_args.args,('project-test-id','PROJECT_TEST',items))
            self.assertEqual([x['value'] for x in cache.projects['PROJECT_TEST']['templates']],['Text+ personalizado'])
            self.assertEqual(cache.projects['PROJECT_TEST']['verifiedIds'],{'Text+ personalizado':'title-id'})
            self.assertEqual(cache.progress['percent'],100)
            self.assertIn('PROJECT_TEST',cache.scanned)

    def test_partial_library_does_not_erase_durable_cache_and_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.json'
            cache=self.make_cache(path,[item('Viejo','title-id'),item('Ajuste','adjust-id')])
            cache.persist();before=path.read_bytes()
            with patch.object(module,'inspect_catalog',return_value=catalog(covered=('adjust-id',),generators=600)),patch.object(module,'inspect_local_library',return_value=catalog(generators=0)):
                cache.scan()
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(cache.projects['PROJECT_TEST']['templates'][0]['value'],'Viejo')
            self.assertNotIn('PROJECT_TEST',cache.scanned)
            self.assertEqual(cache.progress['phase'],'waiting')
            self.assertIn('sin verificar',cache.progress['message'])

    def test_fully_verified_removal_can_replace_old_list_with_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=self.make_cache(Path(folder)/'cache.json',[item('Ajuste','adjust-id')])
            with patch.object(module,'inspect_catalog',return_value=catalog(covered=('adjust-id',),generators=1)),patch.object(module,'inspect_local_library') as reader:
                cache.scan()
            reader.assert_not_called()
            self.assertEqual(cache.projects['PROJECT_TEST']['templates'],[])
            self.assertEqual(cache.progress['percent'],100)

    def test_partial_export_preserves_verified_title_while_missing_ids_use_library(self):
        with tempfile.TemporaryDirectory() as folder:
            title,new,adjust=item('Viejo','title-id'),item('Nuevo','new-id'),item('Ajuste','adjust-id')
            cache=self.make_cache(Path(folder)/'cache.json',[title,new,adjust])
            with patch.object(module,'inspect_catalog',return_value=catalog(('title-id',),('title-id','adjust-id'),2)),patch.object(module,'inspect_local_library',return_value=catalog(('new-id',),('new-id',),1)) as reader:
                cache.scan()
            self.assertEqual(reader.call_args.args[2],[new])
            self.assertEqual([x['value'] for x in cache.projects['PROJECT_TEST']['templates']],['Viejo','Nuevo'])

    def test_unavailable_library_keeps_old_list(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=self.make_cache(Path(folder)/'cache.json',[item('Nuevo','new-id')])
            with patch.object(module,'inspect_catalog',return_value=catalog(generators=600)),patch.object(module,'inspect_local_library',side_effect=TimeoutError('Biblioteca ocupada')):
                cache.scan()
            self.assertEqual(cache.projects['PROJECT_TEST']['templates'][0]['value'],'Viejo')
            self.assertNotIn('PROJECT_TEST',cache.scanned)

    def selection_cache(self,path,candidates,project='project-test-id'):
        def call(payload,timeout):
            return {'GetTimelineInfo':{'projectName':'PROJECT_TEST'},'GetTemplates':candidates,
                'GetTemplateScanStatus':{'complete':True,'projectKey':project}}[payload['func']]
        cache=module.TemplateCache(path,call)
        cache.projects={'PROJECT_TEST':{'templates':[{'label':'Mi Text+','value':'Mi Text+'}],
            'verifiedIds':{'Mi Text+':'title-id'},'projectKey':'project-test-id'}}
        return cache

    def test_selection_default_uses_verified_title_not_first_adjustment(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=self.selection_cache(Path(folder)/'cache.json',[item('Ajuste','adjust-id'),item('Mi Text+','title-id')])
            self.assertEqual(cache.validate_selection('')['mediaId'],'title-id')
            with self.assertRaisesRegex(RuntimeError,'no está verificado'):cache.validate_selection('Ajuste')

    def test_same_named_replacement_or_other_project_cannot_use_old_title(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=self.selection_cache(Path(folder)/'cache.json',[item('Mi Text+','replacement-adjust-id')])
            with self.assertRaisesRegex(RuntimeError,'renombrado o eliminado'):cache.validate_selection('Mi Text+')
            cache=self.selection_cache(Path(folder)/'cache.json',[item('Mi Text+','title-id')],'other-project-id')
            with self.assertRaisesRegex(RuntimeError,'cambió de proyecto'):cache.validate_selection('Mi Text+')

if __name__=='__main__':unittest.main(verbosity=2)
