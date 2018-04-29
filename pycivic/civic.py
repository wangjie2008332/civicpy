import requests
import importlib

MODULE = importlib.import_module('pycivic.civic')

API_URL = 'https://civicdb.org/api'

UNMARKED_PLURALS = {'evidence'}

CIVIC_TO_PYCLASS = {
    'evidence_items': 'evidence'
}

def pluralize(element_type):
    if element_type in UNMARKED_PLURALS:
        return element_type
    if element_type.endswith('s'):
        return element_type
    return element_type + 's'

def search_url(element):
    return '/'.join([API_URL, element, 'search'])


def snake_to_camel(snake_string):
    words = snake_string.split('_')
    cap_words = [x.capitalize() for x in words]
    return ''.join(cap_words)


def map_to_class_string(element_type):
    x = CIVIC_TO_PYCLASS.get(element_type, element_type)
    if x == 'evidence_item':
        x = 'evidence'
    return snake_to_camel(x)


def element_lookup_by_id(element_type, element_id):
    e_string = pluralize(element_type.lower())
    if e_string == 'evidence':
        e_string = 'evidence_items'
    url = '/'.join([API_URL, e_string, str(element_id)])
    resp = requests.get(url)
    resp.raise_for_status()
    resp_dict = resp.json()
    return resp_dict


class CivicRecord:

    SIMPLE_FIELDS = {'id', 'type'}
    COMPLEX_FIELDS = set()

    def __init__(self, partial=False, **kwargs):
        self._incomplete = set()
        self.partial = partial
        simple_fields = sorted(self.SIMPLE_FIELDS, reverse=True)
        simple_fields = sorted(simple_fields, key=lambda x: x in CivicRecord.SIMPLE_FIELDS, reverse=True)
        for field in simple_fields:
            try:
                self.__setattr__(field, kwargs[field])
            except KeyError:
                try:
                    object.__getattribute__(self, field)
                except AttributeError:
                    if partial and field not in CivicRecord.SIMPLE_FIELDS:
                        self._incomplete.add(field)     # Allow for incomplete data when partial flag set
                    else:
                        raise AttributeError(f'Expected {field} attribute for {self.type}, none found.')

        for field in self.COMPLEX_FIELDS:
            try:
                v = kwargs[field]
            except KeyError:
                if partial:
                    self._incomplete.add(field)
                    continue
                else:
                    raise AttributeError(f'Expected {field} attribute for {self.type}, none found.')
            is_compound = isinstance(v, list)
            if is_compound:
                class_string = map_to_class_string(field.rstrip('s'))
                cls = getattr(MODULE, class_string, Attribute)
                result = list()
                for data in v:
                    try:
                        data['type'] = data.get('type', field.rstrip('s'))
                    except AttributeError:  # if data has no 'get' method, i.e. not a Dict
                        result.append(v)
                    else:
                        result.append(cls(partial=True, **data))
                self.__setattr__(field, result)
            else:
                cls = getattr(MODULE, map_to_class_string(field), Attribute)
                v['type'] = v.get('type', field)
                self.__setattr__(field, cls(partial=True, **v))

        self.partial = bool(self._incomplete)

    def __repr__(self):
        return f'<CIViC {self.type} {self.id}>'

    def __getattr__(self, item):
        if self.partial and item in self._incomplete:
            self.update()
        return object.__getattribute__(self, item)

    def update(self, allow_partial=True, **kwargs):
        """Updates record and returns True if record is complete after update, else False."""
        if kwargs:
            self.__init__(partial=allow_partial, **kwargs)
            return not self.partial

        resp_dict = element_lookup_by_id(self.type, self.id)
        self.__init__(partial=False, **resp_dict)
        return True


class Variant(CivicRecord):
    SIMPLE_FIELDS = {
        'allele_registry_id',
        'civic_actionability_score',
        'description',
        'entrez_id',
        'entrez_name',
        'gene_id',
        'id',
        'name',
        'type'}
    COMPLEX_FIELDS = {
        'assertions',
        'clinvar_entries',
        'coordinates',
        'errors',
        'evidence_items',
        'hgvs_expressions',
        'lifecycle_actions',
        'provisional_values',
        'sources',
        'variant_aliases',
        'variant_groups',
        'variant_types'}


class Gene(CivicRecord):
    SIMPLE_FIELDS = {'description', 'entrez_id', 'id', 'name', 'type'}
    COMPLEX_FIELDS = {
        'aliases',
        'errors',
        'lifecycle_actions',
        'provisional_values',
        'sources',
        'variants'}


class Evidence(CivicRecord):
    SIMPLE_FIELDS = {
        'clinical_significance',
        'description',
        'drug_interaction_type',
        'evidence_direction',
        'evidence_level',
        'evidence_type',
        'gene_id',
        'id',
        'name',
        'open_change_count',
        'rating',
        'status',
        'type',
        'variant_id',
        'variant_origin'}
    COMPLEX_FIELDS = {
        'assertions',
        'disease',
        'drugs',
        'errors',
        'fields_with_pending_changes',
        'lifecycle_actions',
        'phenotypes',
        'source'}


class Assertion(CivicRecord):
    SIMPLE_FIELDS = {
        'allele_registry_id',
        'amp_level',
        'clinical_significance',
        'description',
        'drug_interaction_type',
        'evidence_direction',
        'evidence_item_count',
        'evidence_type',
        'fda_companion_test',
        'fda_regulatory_approval',
        'id',
        'name',
        'nccn_guideline',
        'nccn_guideline_version',
        'open_change_count',
        'pending_evidence_count',
        'status',
        'summary',
        'type',
        'variant_origin'
    }

    COMPLEX_FIELDS = CivicRecord.COMPLEX_FIELDS.union({
        'acmg_codes',
        'disease',
        'drugs',
        'evidence_items',
        'gene',
        'lifecycle_actions',
        'phenotypes',
        'variant'
    })


class Attribute(CivicRecord):

    SIMPLE_FIELDS = {'type'}
    COMPLEX_FIELDS = set()

    def __repr__(self):
        return f'<CIViC Attribute {self.type}>'

    def __init__(self, **kwargs):
        kwargs['partial'] = False
        for k, v in kwargs.items():
            self.__setattr__(k, v)
        super().__init__(**kwargs)


class Drug(Attribute):
    SIMPLE_FIELDS = CivicRecord.SIMPLE_FIELDS.union({'pubchem_id'})


class Disease(Attribute):
    SIMPLE_FIELDS = CivicRecord.SIMPLE_FIELDS.union({'display_name', 'doid', 'url'})


def get_assertions(assertion_id_list):
    queries = list()
    for assertion_id in assertion_id_list:
        query = {
            'field': 'id',
            'condition': {
                'name': 'is_equal_to',
                'parameters': [
                    assertion_id
                ]
            }
        }
        queries.append(query)
    payload = {
        'operator': 'OR',
        'queries': queries
    }
    url = search_url('assertions')
    response = requests.post(url, json=payload)
    response.raise_for_status()
    assertions = [Assertion(**x) for x in response.json()['results']]
    return assertions
