import unittest
if not  hasattr(unittest.TestCase, 'assertIsInstance'):
    import unittest2 as unittest
import tkp.database as tkpdb
import tkp.database.utils.general as dbgen
import tkp.database.utils.transients as dbt
import tkp.database.utils as dbutils
from tkp.classification.transient import Transient
import tkp.config
import tests.db_subs as db_subs
from tests.decorators import requires_database


class TestTransientRoutines(unittest.TestCase):
    @requires_database()
    def setUp(self):
        self.database = tkpdb.DataBase()
        #self.dataset = tkpdb.DataSet(data={'description':"Trans:"+self._testMethodName},
        #                            database = self.database)

        #self.n_images = 8                
        #self.im_params = db_subs.example_dbimage_datasets(self.n_images)
        #self.db_imgs=[]
        #
        ##Insert transient source extractions, 
        ##Include the non-detection points we expect from using monitoringlist:
        #source_lists=db_subs.example_source_lists(n_images=8,
        #                                          include_non_detections=True)
        #            
        ##print "source_lists:",source_lists
        #for i in range(len(self.im_params)):
        #    print "\ni, im_params[i]:", i, self.im_params[i]
        #for i in range(len(source_lists)):
        #    print "\ni, source_list[i]:", i, source_lists[i]
        #for i in xrange(self.n_images):
        #    self.db_imgs.append(
        #                tkpdb.Image(data=self.im_params[i], 
        #                                    dataset=self.dataset)
        #                        )
        #    print "self.db_imgs[i]:",self.db_imgs[i]
        #    self.db_imgs[i].insert_extracted_sources(source_lists[i])
        #    self.db_imgs[i].associate_extracted_sources(deRuiter_r=3.7)
        #    
        #runcats = self.dataset.runcat_entries()
        #self.assertNotEqual(len(runcats),0)
        #arbitrary_valid_rcid = runcats[0]['runcat']
        #self.dummy_transient = Transient(runcatid = arbitrary_valid_rcid)
        #self.dummy_transient.eta = 2 #Reduced Chi-squared
        #self.dummy_transient.V = 0.5 #Fractional std. dev.
        #self.dummy_transient.trid = None

    def tearDown(self):
        self.database.close()

    def test_single_band_transient_search(self):
        # We have to add a dataset, some images all with some measurements
        # After insertion, and source association, we run the transient search.
        dataset = tkpdb.DataSet(database=self.database,
                                data={'description':"Trans:" + self._testMethodName})
        n_images = 4
        im_params = db_subs.example_dbimage_datasets(n_images)
        TransientSource = db_subs.example_extractedsource_tuple()
        # Set to easy number...
        TransientSource._replace(flux=20e-3)

        measurements = []
        image = []
        for i in range(len(im_params)):
            image.append(tkpdb.Image(database=self.database, dataset=dataset, data=im_params[i]))
            if i == n_images - 2:
                s = TransientSource._replace(flux=20e-2)
            elif i == n_images - 1:
                s = TransientSource._replace(flux=10e-3)
            else:
                s = TransientSource
            measurements.append(s)

            dbgen.insert_extracted_sources(self.database.connection, image[i].id,
                                           [ measurements[-1] ])
            image[-1].associate_extracted_sources()
            freq_bands = dataset.frequency_bands()
            self.assertEqual(len(freq_bands), 1)
            transient_ids, siglevels, transients = dbt.transient_search(
                                            conn=self.database.connection,
                                            dsid=dataset.id,
                                            freq_band=freq_bands[0],
                                            eta_lim=1,
                                            V_lim=0.1,
                                            probability_threshold=0.7,
                                            minpoints=1,
                                            imageid=image[-1].id)
            #print "transient_ids:",transient_ids
            #print "siglevels:",siglevels

        # Check the number of detected transients
        self.assertEqual(len(transients), 1)

        # Check that the bands for the images are the same as the transient's band
        freq_bands = dataset.frequency_bands()
        self.assertEqual(len(freq_bands), 1)
        for tr in transients:
            self.assertEqual(freq_bands[0], tr.band)

        # Check that there is only one runcat source, and that this
        # is the ref in the transient table
        query = """\
        SELECT id
          FROM runningcatalog
         WHERE dataset = %s
        """
        self.database.cursor.execute(query, (dataset.id,))
        runcatids = zip(*self.database.cursor.fetchall())[0]
        self.assertEqual(len(runcatids), 1)
        for tr in transients:
            print "tr.siglevel:", tr.siglevel
            self.assertEqual(runcatids[0], tr.runcatid)

        # Check that the trigger xtrsrc happened in the third image
        query = """\
        select taustart_ts
          from extractedsource x
              ,image i
         where x.image = i.id
           and x.id = (select trigger_xtrsrc
                         from transient t
                             ,runningcatalog r
                        where t.runcat = r.id
                          and r.dataset = %s
                      )
        """
        self.database.cursor.execute(query, (dataset.id,))
        taustart_ts = zip(*self.database.cursor.fetchall())
        self.assertEqual(len(taustart_ts), 1)
        ts = taustart_ts[0][0]
        self.assertEqual(ts, image[2].taustart_ts)

        # Check the variability indices, first eta_int:
        #query = """\
        #select sum((f_int - 0.06) * (f_int-0.06) / (f_int_err * f_int_err)) / 3 
        #  from assocxtrsource a
        #      ,extractedsource x 
        # where a.xtrsrc = x.id 
        #   and a.runcat = 7
        #"""
        query = """\
        select sum((f_int - 0.06) * (f_int - 0.06) / (f_int_err * f_int_err)) / 3
          from assocxtrsource a
              ,extractedsource x
         where a.xtrsrc = x.id
           and a.runcat = (select t.runcat
                             from runningcatalog r
                                  ,transient t
                            where r.id = t.runcat
                              and r.dataset = %s
                          )
        """

    #def test_full_transient_search_routine(self):
    #    for img in self.db_imgs[:]:
    #        tkpdb.utils.transient_search(
    #                 conn = self.database.connection,
    #                 dataset = self.dataset, 
    #                 eta_lim = 1.1,
    #                 V_lim = 0.01,
    #                 probability_threshold = 0.01, 
    #                 imageid = img.id,
    #                 minpoints = 1)
