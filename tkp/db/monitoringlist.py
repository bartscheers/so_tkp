"""
A collection of back end subroutines (mostly SQL queries).

This module contains the routines to deal with flagging and monitoring
of transient candidates, mostly involving the monitoringlist.
"""
import logging
from collections import namedtuple
import time

from tkp.db import general
import tkp.db


logger = logging.getLogger(__name__)
logdir = '/export/scratch2/bscheers/lofar/release1/performance/2013-sp3/napels/10x10000/log'


def get_nulldetections(image_id, deRuiter_r):
    """
    Returns the runningcatalog sources which:

      * Do not have a counterpart in the extractedsources of the current
        image;
      * Have been seen (in any band) in a timestep earlier than that of the
        current image.

    NB This is run *prior* to source association.

    We do not have to take into account associations with monitoringlist
    sources, since they have been added to extractedsources at the beginning
    of the association procedures (marked as extract_type=1 sources), and so
    they must have an occurence in extractedsource and runcat.

    Output: list of tuples [(runcatid, ra, decl)]
    """
    # The first subquery looks for extractedsources without runcat associations.
    # The second subquery looks for runcat entries we expect to see in this image.
    # Note about the second subquery that we want the first detection of a runcat 
    # source to be in the same skyregion as the current image. 
    # NB extra clause on x.image is necessary for performance reasons.
    query = """\
SELECT r1.id
      ,r1.wm_ra
      ,r1.wm_decl
  FROM runningcatalog r1
      ,image i1
 WHERE i1.id = %(imgid)s
   AND i1.dataset = r1.dataset
   AND r1.id NOT IN (SELECT r.id
                       FROM runningcatalog r
                           ,extractedsource x
                           ,image i
                      WHERE i.id = %(imgid)s
                        AND x.image = i.id
                        AND x.image = %(imgid)s
                        AND i.dataset = r.dataset
                        AND r.zone BETWEEN CAST(FLOOR(x.decl - i.rb_smaj) AS INTEGER)
                                       AND CAST(FLOOR(x.decl + i.rb_smaj) AS INTEGER)
                        AND r.wm_decl BETWEEN x.decl - i.rb_smaj
                                          AND x.decl + i.rb_smaj
                        AND r.wm_ra BETWEEN x.ra - alpha(i.rb_smaj, x.decl)
                                        AND x.ra + alpha(i.rb_smaj, x.decl)
                        AND SQRT(  (x.ra - r.wm_ra) * COS(RADIANS((x.decl + r.wm_decl)/2))
                                 * (x.ra - r.wm_ra) * COS(RADIANS((x.decl + r.wm_decl)/2))
                                 / (x.uncertainty_ew * x.uncertainty_ew + r.wm_uncertainty_ew * r.wm_uncertainty_ew)
                                + (x.decl - r.wm_decl) * (x.decl - r.wm_decl)
                                 / (x.uncertainty_ns * x.uncertainty_ns + r.wm_uncertainty_ns * r.wm_uncertainty_ns)
                                ) < %(drrad)s
                    )
   AND r1.id IN (SELECT r2.id
                   FROM runningcatalog r2
                       ,assocskyrgn a2 
                       ,image i2
                       ,extractedsource x
                       ,image i3
                  WHERE i2.id = %(imgid)s
                    AND a2.skyrgn = i2.skyrgn
                    AND a2.runcat = r2.id 
                    AND r2.xtrsrc = x.id
                    AND x.image = i3.id
                    AND i3.taustart_ts < i2.taustart_ts
                )
"""
    qry_params = {'imgid':image_id, 'drrad': deRuiter_r}
    logfile = open(logdir + '/' + get_nulldetections.__name__ + '.log', 'a')
    start = time.time()
    cursor = tkp.db.execute(query, qry_params)
    q_end = time.time() - start
    commit_end = time.time() - start
    logfile.write(str(image_id) + "," + str(q_end) + "," + str(commit_end) + "\n")
    results = zip(*cursor.fetchall())
    if len(results) != 0:
        return zip(list(results[1]), list(results[2]))
        #maxbeam = max(results[3][0],results[4][0]) # all bmaj & bmin are the same
    else:
        return []


def adjust_transients_in_monitoringlist(image_id, transients):
    """Adjust transients in monitoringlist, by either adding or
    updating them

    """
    _update_known_transients_in_monitoringlist(transients)
    _insert_new_transients_in_monitoringlist(image_id)


def _update_known_transients_in_monitoringlist(transients):
    """Update transients in monitoringlist"""
    query = """\
    UPDATE monitoringlist
       SET ra = %(wm_ra)s
          ,decl = %(wm_decl)s
      WHERE runcat = %(runcat)s
    """
    upd = 0
    for entry in transients:
        logfile = open(logdir + '/' + _update_known_transients_in_monitoringlist.__name__ + '.log', 'a')
        start = time.time()
        cursor = tkp.db.execute(query, entry, commit=True)
        q_end = time.time() - start
        commit_end = time.time() - start
        logfile.write(str(image_id) + "," + str(q_end) + "," + str(commit_end) + "\n")
        upd += cursor.rowcount
    if upd > 0:
        logger.info("Updated %s known transients in monitoringlist" % (upd,))


def _insert_new_transients_in_monitoringlist(image_id):
    """
    Copy newly identified transients from transients table into monitoringlist.

    We grab the transients and check that their runcat ids are not in the
    monitoringlist.
    """
    query = """\
INSERT INTO monitoringlist
  (runcat
  ,ra
  ,decl
  ,dataset
  )
  SELECT t.runcat
        ,r.wm_ra
        ,r.wm_decl
        ,r.dataset
    FROM transient t
        ,runningcatalog r
        ,image i
   WHERE t.runcat = r.id
     AND r.dataset = i.dataset
     AND i.id = %(image_id)s
     AND t.runcat NOT IN (SELECT m0.runcat
                            FROM monitoringlist m0
                                ,runningcatalog r0
                                ,image i0
                           WHERE m0.runcat = r0.id
                             AND r0.dataset = i0.dataset
                             AND i0.id = %(image_id)s
                         )
"""
    logfile = open(logdir + '/' + _insert_new_transients_in_monitoringlist.__name__ + '.log', 'a')
    start = time.time()
    cursor = tkp.db.execute(query, {'image_id': image_id}, commit=True)
    q_end = time.time() - start
    commit_end = time.time() - start
    logfile.write(str(image_id) + "," + str(q_end) + "," + str(commit_end) + "\n")
    ins = cursor.rowcount
    if ins == 0:
        logger.info("No new transients inserted in monitoringlist")
    else:
        logger.info("Inserted %s new transients in monitoringlist" % (ins,))


def add_nulldetections(image_id):
    """
    Add null detections (intermittent) sources to monitoringlist.

    Null detections are picked up by the source association and
    added to extractedsource table to undergo normal processing.

    Variable or not, intermittent sources are interesting enough
    to be added to the monitoringlist.

    Insert checks whether runcat ref of source exists
    """

    # TODO:
    # Do we need to take care of updates here as well (like the adjust_transients)?
    # Or is that correctly done in update monlist

    # Optimise by using image_id for image and extractedsource
    # extract_type = 1 -> the null detections (forced fit) in extractedsource
    #Note extra clauses on image id ARE necessary (MonetDB performance quirks)
    query = """\
INSERT INTO monitoringlist
  (runcat
  ,ra
  ,decl
  ,dataset
  )
  SELECT r.id AS runcat
        ,r.wm_ra AS ra
        ,r.wm_decl AS decl
        ,r.dataset
    FROM extractedsource x
        ,image i
        ,runningcatalog r
        ,assocxtrsource a
   WHERE x.image = %(image_id)s
     AND x.image = i.id
     AND i.id = %(image_id)s
     AND i.dataset = r.dataset
     AND r.id = a.runcat
     AND a.xtrsrc = x.id
     AND x.extract_type = 1
     AND NOT EXISTS (SELECT m0.runcat
                       FROM extractedsource x0
                           ,image i0
                           ,runningcatalog r0
                           ,assocxtrsource a0
                           ,monitoringlist m0
                      WHERE x0.image = %(image_id)s
                        AND x0.image = i0.id
                        AND i0.id = %(image_id)s
                        AND i0.dataset = r0.dataset
                        AND r0.id = a0.runcat
                        AND a0.xtrsrc = x0.id
                        AND x0.extract_type = 1
                        AND r0.id = m0.runcat
                    )
"""
    logfile = open(logdir + '/' + add_nulldetections.__name__ + '.log', 'a')
    start = time.time()
    cursor = tkp.db.execute(query, {'image_id': image_id}, commit=True)
    q_end = time.time() - start
    commit_end = time.time() - start
    logfile.write(str(image_id) + "," + str(q_end) + "," + str(commit_end) + "\n")
    ins = cursor.rowcount
    if ins > 0:
        logger.info("Added %s forced fit null detections to monlist" % (ins,))


def add_manual_entry_to_monitoringlist(dataset_id, ra, dec):
    """
    Add manual entry to monitoringlist.

    In this case, the runcat_id defaults to null initially,
    since there is no associated source yet.
    (This is updated when we perform our first forced extraction
    at these co-ordinates.)
    """
    query = """\
INSERT INTO monitoringlist
  (ra
  ,decl
  ,dataset
  ,userentry
  )
  SELECT %s
        ,%s
        ,%s
        ,TRUE
"""
    cursor = tkp.db.execute(query, commit=True)
