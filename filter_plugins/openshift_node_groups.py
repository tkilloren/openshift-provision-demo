def provision_to_openshift_node_groups(source, delim='='):
    ''' Returns definition of openshift_node_groups from openshift_provision_node_groups '''
    return [ {
        'name': 'node-config-' + k,
        'labels': v['labels'],
        'edits': []
    } for k, v in source.items()]

class FilterModule(object):
    ''' OpenShift Filters for selector strings '''

    # pylint: disable=no-self-use, too-few-public-methods
    def filters(self):
        ''' Returns filters provided by this class '''
        return {
            'provision_to_openshift_node_groups': provision_to_openshift_node_groups
        }
