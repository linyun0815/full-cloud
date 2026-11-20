package cn.full.cloud.module.pms.dal.mysql.pm.project;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.pms.dal.dataobject.pm.project.PmsProjectAnnouncementDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface PmsProjectAnnouncementMapper extends BaseMapperX<PmsProjectAnnouncementDO> {

    default List<PmsProjectAnnouncementDO> selectListByProjectId(Long projectId) {
        return selectList(new LambdaQueryWrapperX<PmsProjectAnnouncementDO>()
                .eq(PmsProjectAnnouncementDO::getProjectId, projectId)
                .orderByDesc(PmsProjectAnnouncementDO::getCreateTime)
                .orderByDesc(PmsProjectAnnouncementDO::getId));
    }

    default void deleteByProjectId(Long projectId) {
        delete(new LambdaQueryWrapperX<PmsProjectAnnouncementDO>()
                .eq(PmsProjectAnnouncementDO::getProjectId, projectId));
    }

}
