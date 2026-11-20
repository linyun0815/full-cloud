package cn.full.cloud.module.pms.dal.mysql.pm.workitem;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.pms.dal.dataobject.pm.workitem.PmsWorkItemLabelDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface PmsWorkItemLabelMapper extends BaseMapperX<PmsWorkItemLabelDO> {

    default List<PmsWorkItemLabelDO> selectListByName(String name) {
        return selectList(new LambdaQueryWrapperX<PmsWorkItemLabelDO>()
                .likeIfPresent(PmsWorkItemLabelDO::getName, name)
                .orderByAsc(PmsWorkItemLabelDO::getCreateTime)
                .orderByAsc(PmsWorkItemLabelDO::getId));
    }

}
