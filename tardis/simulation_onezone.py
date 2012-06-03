import plasma
import initialize
import atomic
import line
import photon
import constants
import numpy as np
import montecarlo_multizone
import time
import model
import os
import logging


def run_multizone(conn, fname, max_atom=30, max_ion=30):
    initial_config = initialize.read_simple_config(fname)


    abundances = plasma.named2array_abundances(initial_config['abundances'], max_atom)
    atomic_model = atomic.KuruczMacroAtomModel.from_db(conn)
    line_list = line.read_line_list(conn)
    line2level = line_list['global_level_id_upper'] - 1
    atomic_model.macro_atom.read_nus(line_list['nu'])
    
    w7model = model.MultiZoneRadial.from_w7(initial_config['time_exp'])
    t_rad = initial_config['t_outer']
    t_inner = t_rad
    surface_inner = 4 * np.pi * w7model.r_inner[0]**2
    volume = (4./3) * np.pi * (w7model.r_outer**3 - w7model.r_inner**3)
    w7model.set_line_list(line_list)
    w7model.set_atomic_model(atomic_model)
    w7model.read_abundances_uniform(abundances)
    #w7model.read_w7_abundances()
    w7model.initialize_plasmas(t_rad)
    
    i = 0
    print "starting", t_rad
    track_ws = []
    track_t_rads = []
    track_t_inner = []

    while True:
        start_time = time.time()
        track_t_rads.append(w7model.t_rads.copy())
        track_t_inner.append(t_inner)
        track_ws.append(w7model.ws.copy())
        i+=1
        if i > initial_config['iterations']: break
        if os.path.exists('stop_file') or i == initial_config['iterations']:
            no_of_packets = initial_config['no_of_spectrum_packets']
            energy_of_packet = 1. / no_of_packets
        else:
            no_of_packets = initial_config['no_of_calibration_packets']
            energy_of_packet = 1. / no_of_packets

        #return sn_plasma
        
        tau_sobolevs = w7model.calculate_tau_sobolevs()
        transition_probabilities = w7model.calculate_transition_probabilities(tau_sobolevs)
        nu_input = np.sort(photon.random_blackbody_nu(t_inner, nu_range=(1e8*constants.c / 1, 1e8*constants.c/ 100000.), size=no_of_packets))[::-1]
        mu_input = np.sqrt(np.random.random(no_of_packets))

        print "calculating transition probabilities"
        
        
        print "running montecarlo"
        nu, energy, nu_reabsorbed, energy_reabsorbed, j_estimators, nubar_estimators = \
                                    montecarlo_multizone.run_simple_oned(nu_input,
                                                                mu_input,
                                                                line_list['nu'],
                                                                tau_sobolevs,
                                                                w7model.r_inner,
                                                                w7model.r_outer,
                                                                w7model.v_inner,
                                                                w7model.electron_densities,
                                                                energy_of_packet,
                                                                transition_probabilities,
                                                                w7model.atomic_model.macro_atom.transition_type_total,
                                                                w7model.atomic_model.macro_atom.target_level_total,
                                                                w7model.atomic_model.macro_atom.target_line_total,
                                                                w7model.atomic_model.macro_atom.level_references,
                                                                line2level)
        
        new_t_rads = constants.trad_estimator_constant * nubar_estimators / j_estimators
        new_ws = constants.w_estimator_constant * j_estimators / (initial_config['time_simulation'] * new_t_rads**4 * volume)
        
        emitted_energy_fraction = np.sum(energy[nu != 0]) / 1.
        
        
        new_t_inner = (initial_config['luminosity_outer'] / (emitted_energy_fraction * constants.sigma_sb * surface_inner ))**.25
        
        for new_t_rad, new_w, old_trad, old_w in zip(new_t_rads, new_ws, w7model.t_rads, w7model.ws):
            print "new_trad / t_rad %.2f / %.2f, new_w/w %.5f %.5f" % (new_t_rad, old_trad, new_w, old_w)
        print '\n\n---'
        print "new_tinner / t_inner  %.2f / %.2f" %(new_t_inner, t_inner)
        w7model.ws = (new_ws + w7model.ws) * .5
        w7model.t_rads = (new_t_rads + w7model.t_rads) * .5
        t_inner = (new_t_inner + t_inner) * .5
        w7model.update_model(w7model.t_rads, w7model.ws)
        
        print "took %.2f s" % (time.time() - start_time)
        
    return nu_input, energy_of_packet, nu, energy, nu_reabsorbed, energy_reabsorbed, track_t_rads, track_ws, track_t_inner
    