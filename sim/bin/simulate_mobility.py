#!/usr/bin/env python3
"""Given settings, simulates mobility patterns of a population, saving the results to a JSON."""

import argparse
from datetime import datetime
import json
import numpy as np
from pathlib import Path
import pickle
import random

from lib.distributions import CovidDistributions
from lib.dynamics import DiseaseModel
from lib.measures import Interval, MeasureList, SocialDistancingForPositiveMeasure
from lib.mobilitysim import MobilitySimulator


def get_site_types():
    path = Path(__file__).parents[1] / 'lib/data/queries'
    return dict(enumerate(p.stem for p in path.glob('*.txt') if p.stem != 'buildings'))

site_dict = get_site_types()
# default site types:
# site_dict = {0: 'education', 1: 'social', 2: 'bus_stop', 3: 'office', 4: 'supermarket'}


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('settings', help = 'settings pickle file for MobilitySimulator')
    parser.add_argument('-o', '--output-file', default = None, help = 'output JSON file')
    parser.add_argument('-t', '--max-time', type = float, default = 168, help = 'time duration (in hours) to simulate')
    parser.add_argument('-s', '--seed', type = int, default = None, help = 'random seed')
    args = parser.parse_args()

    now = datetime.now()
    if args.output_file is None:
        args.output_file = now.strftime('sim_%Y%m%d%H%M%S.json')

    # load settings
    with open(args.settings, 'rb') as f:
        settings = pickle.load(f)

    disease_settings = settings['disease']
    age_ranges = disease_settings['age_ranges']

    def rand_age_in_category(cat):
        return random.randint(*age_ranges[cat])

    # simulate mobility
    mob = MobilitySimulator(**settings['mobility'])
    mob.verbose = True

    print(f'{mob.num_people} people, {mob.num_sites} sites, {args.max_time} hours')

    print(f'Simulating mobility...')
    mob.simulate(max_time=args.max_time, seed=args.seed)
    traces = mob.all_mob_traces
    visits = [{'person': v.indiv, 'site': v.site, 'time': v.t_from, 'dur' : v.duration} for v in traces]
    num_visits = len(visits)
    print(f'{num_visits} visits occurred.')

    # for people, simulate random age in the appropriate range
    if args.seed is not None:
        random.seed(2 * args.seed)
    people = [{'id': i, 'age': rand_age_in_category(cat)} for (i, cat) in enumerate(mob.people_age)]
    sites = [{'id': j, 'type': int(tp), 'lat': lat, 'long': long} for (j, (tp, (lat, long))) in enumerate(zip(mob.site_type, mob.site_loc))]
    assert len(people) == mob.num_people
    assert len(sites) == mob.num_sites

    # simulate disease transmission
    fatality_rates_by_age = np.array(disease_settings['fatality_rates_by_age'])
    distributions = CovidDistributions(fatality_rates_by_age=fatality_rates_by_age)
    testing_params = disease_settings['testing_params']
    testing_params['testing_t_window'] = [0.0, args.max_time]
    # standard measure of positives staying isolated
    measure_list = MeasureList([SocialDistancingForPositiveMeasure(t_window=Interval(0.0, args.max_time), p_stay_home=1.0)])

    print('Simulating disease...')
    sim = DiseaseModel(mob, distributions)
    sim.launch_epidemic(
        params=disease_settings['model_params'],
        initial_counts=disease_settings['initial_seeds'],
        testing_params=testing_params,
        measure_list=measure_list,
        verbose=False)
    tests = [{'person': test.person, 'time': test.time, 'result': int(test.result)} for test in sim.test_log]

    # save data to JSON
    data = {
        'sim_time': now.isoformat(),
        'mode': mob.mode,
        'num_site_types': mob.num_site_types,
        'num_people': mob.num_people,
        'num_sites': mob.num_sites,
        'num_visits' : num_visits,
        'site_types': site_dict,
        'people': people,
        'sites': sites,
        'visits': visits,
        'tests': tests
    }

    print(f'Saving data to {args.output_file}')
    with open(args.output_file, 'w') as f:
        json.dump(data, f, indent=1)

    print('DONE!')
