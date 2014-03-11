
"""
A collection of back end db query subroutines used for unittesting
"""
from tkp.db import execute


def dataset_images(dataset_id, database=None):
    q = "SELECT id FROM image WHERE dataset=%(dataset)s LIMIT 1"
    args = {'dataset': dataset_id}
    cursor = execute(q, args)
    image_ids = [x[0] for x in cursor.fetchall()]
    return image_ids


def convert_to_cartesian(conn, ra, decl):
    """Returns tuple (x,y,z)"""
    qry = """SELECT x,y,z FROM cartesian(%s, %s)"""
    curs = conn.cursor()
    curs.execute(qry, (ra, decl))
    return curs.fetchone()

def evolved_var_indices(db, dataset):
    query = """\
    select a.runcat
          ,a.xtrsrc
          ,a.v_int
          ,a.eta_int
      from assocxtrsource a
          ,extractedsource x
          ,image i
          ,runningcatalog r
     where a.xtrsrc = x.id
       and x.image = i.id
       and i.dataset = %(dataset)s
       and a.runcat = r.id
    order by /*a.runcat
            ,i.taustart_ts*/
             r.wm_ra
            ,r.wm_decl
            ,a.v_int
    """
    db.cursor.execute(query, {'dataset': dataset})
    result = zip(*db.cursor.fetchall())
    return result

def evolved_var_indices_1_to_1_or_n(db, dataset):
    query = """\
    select a.runcat
          ,a.xtrsrc
          ,a.v_int
          ,a.eta_int
      from assocxtrsource a
          ,extractedsource x
          ,image i
          ,runningcatalog r
     where a.xtrsrc = x.id
       and x.image = i.id
       and i.dataset = %(dataset)s
       and a.runcat = r.id
    order by r.wm_ra
            ,i.taustart_ts
    """
    db.cursor.execute(query, {'dataset': dataset})
    result = zip(*db.cursor.fetchall())
    return result

